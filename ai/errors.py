# -*- coding: utf-8 -*-
# common_lib/ai/errors.py

from __future__ import annotations

from typing import Optional


class AIError(Exception):
    """common_lib.ai の基底例外"""
    pass


class InvalidRequestError(AIError):
    """入力不備・引数不正など（リトライしても直らない）"""
    pass


class TimeoutError(AIError):
    """タイムアウト"""
    pass


class InvalidResponseError(AIError):
    """レスポンス形式が想定と違う／必要フィールド欠落"""
    pass


class ProviderError(AIError):
    """
    プロバイダ側が返したエラー。
    status_code / request_id を保持できるようにする。
    """

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        request_id: Optional[str] = None,
        raw: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.request_id = request_id
        self.raw = raw


class RetryableError(ProviderError):
    """429/5xx 等、リトライで改善しうるエラー"""
    pass
