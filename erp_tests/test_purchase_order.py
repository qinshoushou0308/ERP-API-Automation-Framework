import json
import time
from decimal import Decimal

import allure
import pytest
import requests

from base.apiutil import RequestBase
from common.readyaml import ReadYamlData, get_testcase_yaml


ERP_HOST = "http://127.0.0.1:9999/jshERP-boot"
AUTOMATION_REMARK = "API_AUTOMATION_TEST"
ERP_WRITE_INTERVAL_SECONDS = 2.05
_last_erp_write_completed_at = time.monotonic()


def run_yaml_case(file_path, is_write=False):
    if is_write:
        wait_for_next_erp_write_window()
    try:
        case = get_testcase_yaml(file_path)[0]
        RequestBase().specification_yaml(case[0], case[1])
    finally:
        if is_write:
            mark_erp_write_complete()


def wait_for_next_erp_write_window():
    # ERP invalidates the session when the same user writes to the same module
    # twice in one second. Guard before every write, including across test cases.
    elapsed = time.monotonic() - _last_erp_write_completed_at
    remaining = ERP_WRITE_INTERVAL_SECONDS - elapsed
    if remaining > 0:
        time.sleep(remaining)


def mark_erp_write_complete():
    global _last_erp_write_completed_at
    _last_erp_write_completed_at = time.monotonic()


@pytest.fixture(scope="module")
def logged_in_to_erp():
    run_yaml_case("./erp_tests/data/login.yaml")


def find_generated_document(headers, document_type, sub_type, number):
    search = {
        "type": document_type,
        "subType": sub_type,
        "number": number,
    }
    response = requests.get(
        f"{ERP_HOST}/depotHead/list",
        headers=headers,
        params={"search": json.dumps(search, ensure_ascii=False),
                "currentPage": 1, "pageSize": 10},
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json().get("data", {}).get("rows", [])
    if not rows:
        return None

    document = rows[0]
    if document.get("remark") != AUTOMATION_REMARK:
        raise RuntimeError(f"拒绝清理非自动化单据：{number}")
    return document


def remove_generated_document(headers, document, document_name):
    document_id = str(document["id"])
    if document.get("status") == "1":
        wait_for_next_erp_write_window()
        unaudit_response = requests.post(
            f"{ERP_HOST}/depotHead/batchSetStatus",
            headers=headers,
            json={"status": "0", "ids": document_id},
            timeout=10,
        )
        mark_erp_write_complete()
        unaudit_response.raise_for_status()
        if unaudit_response.json().get("code") != 200:
            raise RuntimeError(f"ERP 自动化{document_name}反审核失败")
    if document.get("status") in {"0", "1"}:
        wait_for_next_erp_write_window()
        delete_response = requests.delete(
            f"{ERP_HOST}/depotHead/delete",
            headers=headers,
            params={"id": document_id},
            timeout=10,
        )
        mark_erp_write_complete()
        delete_response.raise_for_status()
        if delete_response.json().get("code") != 200:
            raise RuntimeError(f"ERP 自动化{document_name}清理失败")


@pytest.fixture
def cleanup_generated_purchase_documents(logged_in_to_erp):
    yield

    # Cleanup uses a fresh session so it still works after a mid-flow loginOut.
    run_yaml_case("./erp_tests/data/login.yaml")
    extracted = ReadYamlData("./extract.yaml").get_yaml_data or {}
    token = extracted.get("erp_access_token")
    headers = {"X-Access-Token": token}

    receipt_suffix = extracted.get("erp_receipt_suffix")
    if receipt_suffix:
        receipt = find_generated_document(
            headers, "入库", "采购", f"CGRK{receipt_suffix}"
        )
        if receipt:
            remove_generated_document(headers, receipt, "采购入库单")

    order_suffix = extracted.get("erp_order_suffix")
    if order_suffix:
        order = find_generated_document(
            headers, "其它", "采购订单", f"CGDD{order_suffix}"
        )
        if order:
            remove_generated_document(headers, order, "采购订单")


@pytest.mark.erp
@allure.feature("ERP 采购业务")
class TestPurchaseOrder:
    @pytest.mark.smoke
    @pytest.mark.p0
    @allure.story("登录")
    def test_erp_login(self, logged_in_to_erp):
        assert logged_in_to_erp is None

    @pytest.mark.smoke
    @pytest.mark.p1
    @allure.story("采购订单查询")
    @pytest.mark.parametrize(
        "base_info,testcase",
        get_testcase_yaml("./erp_tests/data/purchase_order_query.yaml"),
    )
    def test_query_completed_purchase_order(
        self, logged_in_to_erp, base_info, testcase
    ):
        allure.dynamic.title(testcase["case_name"])
        RequestBase().specification_yaml(base_info, testcase)

    @pytest.mark.regression
    @pytest.mark.p0
    @allure.story("采购订单完整生命周期")
    def test_purchase_order_lifecycle(self, cleanup_generated_purchase_documents):
        steps = [
            ("生成唯一采购订单号", "purchase_order_number.yaml", False),
            ("新增采购订单", "purchase_order_create.yaml", True),
            ("查询并提取订单 ID", "purchase_order_query_created.yaml", False),
            ("审核采购订单", "purchase_order_audit.yaml", True),
            ("验证审核状态", "purchase_order_query_audited.yaml", False),
            ("反审核采购订单", "purchase_order_unaudit.yaml", True),
            ("删除自动化测试数据", "purchase_order_delete.yaml", True),
        ]
        for title, file_name, is_write in steps:
            with allure.step(title):
                run_yaml_case(f"./erp_tests/data/{file_name}", is_write)

    @pytest.mark.regression
    @pytest.mark.inventory
    @pytest.mark.p0
    @allure.story("采购入库库存校验")
    def test_purchase_receipt_increases_stock(
        self, cleanup_generated_purchase_documents
    ):
        with allure.step("记录采购入库前库存"):
            run_yaml_case("./erp_tests/data/stock_before_purchase_receipt.yaml")

        steps = [
            ("生成采购订单号", "purchase_order_number.yaml", False),
            ("新增采购订单", "purchase_order_create.yaml", True),
            ("查询并提取采购订单 ID", "purchase_order_query_created.yaml", False),
            ("提取采购订单明细 ID", "purchase_order_detail.yaml", False),
            ("审核采购订单", "purchase_order_audit.yaml", True),
            ("生成采购入库单号", "purchase_receipt_number.yaml", False),
            ("从采购订单生成采购入库单", "purchase_receipt_create.yaml", True),
            ("查询并提取采购入库单 ID", "purchase_receipt_query_created.yaml", False),
            ("审核采购入库单", "purchase_receipt_audit.yaml", True),
            ("验证采购入库单审核状态", "purchase_receipt_query_audited.yaml", False),
        ]
        for title, file_name, is_write in steps:
            with allure.step(title):
                run_yaml_case(f"./erp_tests/data/{file_name}", is_write)

        with allure.step("验证仓库1中商品1001的库存增加1"):
            run_yaml_case("./erp_tests/data/stock_after_purchase_receipt.yaml")
            reader = ReadYamlData()
            stock_before = Decimal(str(reader.get_extract_yaml(
                "erp_stock_before_receipt"
            )))
            stock_after = Decimal(str(reader.get_extract_yaml(
                "erp_stock_after_receipt"
            )))
            assert stock_after == stock_before + Decimal("1")

        cleanup_steps = [
            ("反审核采购入库单", "purchase_receipt_unaudit.yaml", True),
            ("删除采购入库单", "purchase_receipt_delete.yaml", True),
            ("反审核采购订单", "purchase_order_unaudit.yaml", True),
            ("删除采购订单", "purchase_order_delete.yaml", True),
        ]
        for title, file_name, is_write in cleanup_steps:
            with allure.step(title):
                run_yaml_case(f"./erp_tests/data/{file_name}", is_write)

        with allure.step("验证清理后库存恢复"):
            run_yaml_case("./erp_tests/data/stock_restored_purchase_receipt.yaml")
            stock_restored = Decimal(str(reader.get_extract_yaml(
                "erp_stock_after_cleanup"
            )))
            assert stock_restored == stock_before

    @pytest.mark.regression
    @pytest.mark.negative
    @pytest.mark.p1
    @allure.story("采购业务异常规则")
    def test_purchase_order_rejects_invalid_operations(
        self, cleanup_generated_purchase_documents
    ):
        with allure.step("记录异常操作前库存"):
            run_yaml_case("./erp_tests/data/stock_before_purchase_receipt.yaml")

        setup_steps = [
            ("生成采购订单号", "purchase_order_number.yaml", False),
            ("新增采购订单", "purchase_order_create.yaml", True),
            ("查询并提取采购订单 ID", "purchase_order_query_created.yaml", False),
            ("提取采购订单明细 ID", "purchase_order_detail.yaml", False),
            ("首次审核采购订单", "purchase_order_audit.yaml", True),
        ]
        for title, file_name, is_write in setup_steps:
            with allure.step(title):
                run_yaml_case(f"./erp_tests/data/{file_name}", is_write)

        invalid_steps = [
            (
                "重复审核被拒绝",
                "purchase_order_repeat_audit_rejected.yaml",
            ),
            (
                "直接删除已审核订单被拒绝",
                "purchase_order_delete_audited_rejected.yaml",
            ),
            ("生成采购入库单号", "purchase_receipt_number.yaml"),
            (
                "采购一件但入库两件被拒绝",
                "purchase_receipt_over_quantity_rejected.yaml",
            ),
        ]
        for title, file_name in invalid_steps:
            with allure.step(title):
                run_yaml_case(
                    f"./erp_tests/data/{file_name}",
                    file_name != "purchase_receipt_number.yaml",
                )

        with allure.step("验证异常请求没有生成入库单或改变库存"):
            reader = ReadYamlData()
            token = reader.get_extract_yaml("erp_access_token")
            receipt_suffix = reader.get_extract_yaml("erp_receipt_suffix")
            headers = {"X-Access-Token": token}
            receipt = find_generated_document(
                headers, "入库", "采购", f"CGRK{receipt_suffix}"
            )
            assert receipt is None

            run_yaml_case("./erp_tests/data/stock_restored_purchase_receipt.yaml")
            stock_before = Decimal(str(reader.get_extract_yaml(
                "erp_stock_before_receipt"
            )))
            stock_after = Decimal(str(reader.get_extract_yaml(
                "erp_stock_after_cleanup"
            )))
            assert stock_after == stock_before
