"""只读采集投放系统配置数据到本地 JSON（不写入远程系统）。"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "data" / "sessions" / "delivery" / "storage.json"
BASE_URL = "http://web.tjhaozew.top"
PAGE_SIZE = 500

BodyFactory = Callable[[int, int], dict]

ENDPOINTS: dict[str, tuple[str, str, BodyFactory | None]] = {
    "cid": (
        "post",
        "/prod-api/ocean/cid/page",
        lambda page, size: {
            "companyName": "",
            "cid": "",
            "remark": "",
            "pageNum": page,
            "pageSize": size,
        },
    ),
    "ad_presets": ("get", "/prod-api/ocean/ad/list", None),
    "open_presets": (
        "get",
        "/prod-api/auto/task/presetConfig/list",
        None,
    ),
    "product_libraries": (
        "get",
        "/prod-api/ocean/platform/list",
        None,
    ),
    "accounts": (
        "post",
        "/prod-api/ocean/fi/list",
        lambda page, size: {
            "fiAdvertiserName": "",
            "fiAdvertiserId": "",
            "ownerUserId": None,
            "pageNum": page,
            "pageSize": size,
        },
    ),
}

_IAA_AD_PRESETS = {
    "B1": "1-iaa漫剧-短剧漫剧库（新美）一零五-一万预算-剧变漫剧",
    "B4": "4-iaa漫剧-小说库（新美）一零五-一万预算-剧变漫剧",
    "B7": "7-iaa漫剧-电商库（新美）一零五-一万预算-剧变漫剧",
    "BX": "bx-iaa漫剧-低设系数短剧漫剧库（新美）1.03-三千预算-剧变漫剧",
}
_IAP_AD_PRESETS = {
    "B1": "付费10全-短剧库-1系数-冰依好剧",
    "B2": "付费3全-短剧库-1系数-剧变漫剧",
}


def _load_token() -> str:
    data = json.loads(STORAGE.read_text(encoding="utf-8"))
    for cookie in data.get("cookies", []):
        if cookie.get("name") == "Admin-Token" and cookie.get("value"):
            return cookie["value"]
    raise SystemExit("未找到投放系统 Admin-Token，请先登录")


def _fetch_all(
    client: httpx.Client,
    method: str,
    path: str,
    body_factory: BodyFactory | None,
) -> tuple[list[dict], int]:
    rows: list[dict] = []
    page = 1
    total = 0
    while True:
        url = f"{path}?pageNum={page}&pageSize={PAGE_SIZE}"
        body = body_factory(page, PAGE_SIZE) if body_factory else None
        response = (
            client.post(url, json=body)
            if method == "post"
            else client.get(url)
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 200:
            raise RuntimeError(data.get("msg") or "接口返回失败")
        total = int(data.get("total") or 0)
        batch = data.get("rows") or []
        rows.extend(batch)
        if not batch or len(rows) >= total:
            break
        page += 1
    return rows, total


def _infer_group(cid: str) -> str:
    """从 CID 名称推断账户组：b1/b2/b4/b7/bx。"""
    match = re.search(r"b([0-9xX])$", cid or "")
    if not match:
        return ""
    value = match.group(1).upper()
    return f"B{value}" if value != "X" else "BX"


def _candidate_ad_preset(row: dict) -> bool:
    name = row.get("preview_name") or row.get("previewName") or ""
    group = row.get("_group") or ""
    if row.get("_is_iap"):
        if group == "B1":
            return name.startswith("付费10全")
        if group == "B2":
            return name.startswith("付费3全")
        return False
    if group == "B1":
        return name.startswith("1-") or name.startswith("123-")
    if group == "B4":
        return name.startswith("4-") or name.startswith("456-")
    if group == "B7":
        return name.startswith("7-") or name.startswith("789-")
    if group == "BX":
        return name.lower().startswith(("bx-", "x-"))
    return False


def _select_open_preset(
    open_rows: list[dict],
    company: str,
    *,
    is_iap: bool,
) -> str:
    """按主体与变现类型选择开户预设；多候选时优先 ty/端付。"""
    expected = "IAP" if is_iap else "IAA"
    matches = [
        row["preset_name"]
        for row in open_rows
        if row["company"] == company
        and row["monetization_type"] == expected
    ]
    if not matches:
        return ""
    for name in matches:
        if is_iap and name.startswith("端付"):
            return name
    for name in matches:
        if "ty" in name:
            return name
    return matches[0]


def _build_snapshot(datasets: dict[str, list[dict]]) -> dict:
    accounts = datasets["accounts"]
    ad_presets = datasets["ad_presets"]
    open_presets = datasets["open_presets"]
    cids = datasets["cid"]
    libraries = datasets["product_libraries"]

    cid_groups: dict[str, dict] = {}
    for account in accounts:
        cid = account.get("cid") or ""
        if not cid:
            continue
        group = cid_groups.setdefault(
            cid,
            {
                "cid": cid,
                "group": _infer_group(cid),
                "company": account.get("oceanCompanyName"),
                "pay_type": account.get("payType"),
                "account_count": 0,
                "sample_name": account.get("fiAdvertiserName"),
                "sample_account_id": account.get("fiAdvertiserId"),
            },
        )
        group["account_count"] += 1

    ad_rows = []
    for preset in ad_presets:
        ad_rows.append(
            {
                "id": preset.get("id"),
                "preview_name": preset.get("previewName"),
                "project_name": preset.get("projectName"),
                "ad_name": preset.get("adName"),
                "delivery_way": (
                    "全域投放"
                    if preset.get("deliveryWay") == 1
                    else "标准投放"
                ),
                "promotion_type": preset.get("promotionTypeStr"),
                "product_type": preset.get("productTypeStr"),
                "optimization_target": preset.get("optimizationTargetStr"),
                "deep_optimization": preset.get("deepOptimizationTargetStr"),
                "bidding_strategy": preset.get("biddingStrategyStr"),
                "roi_coefficient": preset.get("roiCoefficient"),
                "daily_budget": preset.get("dailyBudget"),
                "product_template_id": preset.get("productTemplateId"),
                "custom_douyin_name": preset.get("customDouyinName"),
                "promotion_account_name": preset.get("promotionAccountName"),
            }
        )

    open_rows = []
    for preset in open_presets:
        open_rows.append(
            {
                "id": preset.get("id"),
                "preset_name": preset.get("presetConfigName"),
                "company": preset.get("companyName"),
                "monetization_type": preset.get("monetizationType"),
                "app_type": preset.get("appType"),
                "platform": preset.get("platForm"),
                "created_at": preset.get("createTime"),
            }
        )

    library_rows = []
    for library in libraries:
        library_rows.append(
            {
                "cid": library.get("cid"),
                "company": library.get("companyName"),
                "product_version": library.get("productVersion"),
                "platform_type": library.get("platformType"),
                "platform_name": library.get("platformName"),
                "platform_id": library.get("platformIdStr") or library.get("platformId"),
                "advertiser_id": library.get("fiAdvertiserId"),
                "email": library.get("email"),
                "create_name": library.get("createName"),
                "last_sync": library.get("lastSyncProduct"),
            }
        )

    proposal = []
    for cid_row in cid_groups.values():
        cid = cid_row["cid"]
        group = cid_row["group"]
        is_iaa = str(cid).startswith("端iaa")
        is_iap = str(cid).startswith("端iap")
        candidates = [
            row["preview_name"]
            for row in ad_rows
            if _candidate_ad_preset(
                {**row, "_group": group, "_is_iap": is_iap}
            )
        ]
        open_candidates = [
            row["preset_name"]
            for row in open_rows
            if row["company"] == cid_row.get("company")
            and (
                (is_iaa and row["monetization_type"] == "IAA")
                or (
                    is_iap
                    and group in ("B1", "B2")
                    and row["monetization_type"] == "IAP"
                )
                or (
                    str(cid).lower().startswith("iaap")
                    and row["monetization_type"] == "IAA_AND_IAP"
                )
            )
        ]
        proposal.append(
            {
                "cid": cid,
                "group": group,
                "company": cid_row.get("company"),
                "pay_type": cid_row.get("pay_type"),
                "account_count": cid_row["account_count"],
                "ad_preset": (
                    _IAP_AD_PRESETS.get(group)
                    if is_iap
                    else _IAA_AD_PRESETS.get(group)
                )
                or "",
                "open_preset": _select_open_preset(
                    open_rows,
                    str(cid_row.get("company") or ""),
                    is_iap=is_iap,
                ),
                "douyin_account": "",
                "ad_preset_candidates": candidates,
                "open_preset_candidates": open_candidates,
            }
        )

    return {
        "counts": {
            "cid": len(cids),
            "ad_presets": len(ad_presets),
            "open_presets": len(open_presets),
            "product_libraries": len(libraries),
            "accounts": len(accounts),
        },
        "cid_groups": list(cid_groups.values()),
        "ad_presets": ad_rows,
        "open_presets": open_rows,
        "product_libraries": library_rows,
        "mapping_proposal": proposal,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="采集投放系统配置数据")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "extracted",
        help="输出目录（默认 data/extracted）",
    )
    args = parser.parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    token = _load_token()
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(
        base_url=BASE_URL,
        headers=headers,
        timeout=30,
        follow_redirects=True,
    ) as client:
        datasets: dict[str, list[dict]] = {}
        for name, (method, path, factory) in ENDPOINTS.items():
            rows, total = _fetch_all(client, method, path, factory)
            datasets[name] = rows
            payload = {
                "platform": "delivery",
                "dataset": name,
                "total": total,
                "extracted_count": len(rows),
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "rows": rows,
            }
            target = output_dir / f"delivery_{name}.json"
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"{name}: {len(rows)}/{total} -> {target}")
        snapshot = _build_snapshot(datasets)
        snapshot["extracted_at"] = datetime.now(timezone.utc).isoformat()
        snapshot_target = output_dir / "delivery_snapshot.json"
        snapshot_target.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"snapshot: {snapshot['counts']} -> {snapshot_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
