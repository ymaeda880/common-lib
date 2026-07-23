# -*- coding: utf-8 -*-
# common_lib/ui/synced_controls/page_keys.py
# ============================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyncedControlKeys:
    page_name: str
    pending: str
    project_year_value: str
    project_year_raw: str
    project_no_value: str
    project_no_raw: str
    update_date: str
    last_msg: str
    delete_msg: str


def build_keys(page_name: str) -> SyncedControlKeys:
    p = str(page_name)

    return SyncedControlKeys(
        page_name=p,
        pending=f"{p}__pending",
        project_year_value=f"{p}__project_year_value",
        project_year_raw=f"{p}__project_year_raw",
        project_no_value=f"{p}__project_no_value",
        project_no_raw=f"{p}__project_no_raw",
        update_date=f"{p}__update_date",
        last_msg=f"{p}__last_msg",
        delete_msg=f"{p}__delete_msg",
    )