# -*- coding: utf-8 -*-
# common_lib/ui/synced_controls/form_sync.py
# ============================================================

from __future__ import annotations

import datetime as dt


def clamp_int(value: object, min_value: int, max_value: int) -> int:
    try:
        v = int(value)
    except Exception:
        v = int(min_value)

    return max(int(min_value), min(int(max_value), int(v)))


def format_project_no_3digits(value: object) -> str:
    try:
        v = int(value)
    except Exception:
        v = 0

    return f"{v:03d}"


def sync_year_from_raw(
    st,
    *,
    year_raw_key: str,
    year_value_key: str,
    update_date_key: str,
    year_min: int,
    year_max: int,
) -> None:
    year = clamp_int(
        st.session_state.get(year_raw_key, year_min),
        year_min,
        year_max,
    )

    st.session_state[year_value_key] = year
    st.session_state[year_raw_key] = str(year)
    st.session_state[update_date_key] = dt.date.today().isoformat()


def sync_year_from_slider(
    st,
    *,
    year_raw_key: str,
    year_value_key: str,
    update_date_key: str,
    year_min: int,
    year_max: int,
    year_default: int,
) -> None:
    year = clamp_int(
        st.session_state.get(year_value_key, year_default),
        year_min,
        year_max,
    )

    st.session_state[year_value_key] = year
    st.session_state[year_raw_key] = str(year)
    st.session_state[update_date_key] = dt.date.today().isoformat()


def sync_no_from_raw(
    st,
    *,
    no_raw_key: str,
    no_value_key: str,
    update_date_key: str,
    no_min: int,
    no_max: int,
) -> None:
    no = clamp_int(
        st.session_state.get(no_raw_key, no_min),
        no_min,
        no_max,
    )

    st.session_state[no_value_key] = no
    st.session_state[no_raw_key] = format_project_no_3digits(no)
    st.session_state[update_date_key] = dt.date.today().isoformat()


def sync_no_from_slider(
    st,
    *,
    no_raw_key: str,
    no_value_key: str,
    update_date_key: str,
    no_min: int,
    no_max: int,
    no_default: int,
) -> None:
    no = clamp_int(
        st.session_state.get(no_value_key, no_default),
        no_min,
        no_max,
    )

    st.session_state[no_value_key] = no
    st.session_state[no_raw_key] = format_project_no_3digits(no)
    st.session_state[update_date_key] = dt.date.today().isoformat()