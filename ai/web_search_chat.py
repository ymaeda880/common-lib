# -*- coding: utf-8 -*-
# /Users/macmini2025/projects/common_lib/ai/web_search_chat.py
# ============================================================
# Web検索付きテキスト生成：既存routing/providersは変更しない．
# APIの検索実績・出典・usageを保持し，検索料金を別記する．
# ============================================================
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from common_lib.ai.routing import call_text
from common_lib.ai.types import TextResult, UsageSummary
from common_lib.ai.costs.estimate import estimate_chat_cost_from_usage

PRICING_DATE = '2026-10-18'


# ============================================================
# 出典URLの形式を検証する
# ============================================================
def safe_url(url: str) -> bool:
    if not isinstance(url, str):
        return False

    try:
        return urlsplit(url).scheme in ('http', 'https') and bool(urlsplit(url).netloc)
    except ValueError:
        return False


@dataclass
class SearchReply:
    result: TextResult
    search: dict


# ============================================================
# API応答を辞書・リスト・基本値へ変換する
# Pydanticのシリアライザーを通さず，応答の実データを取り出す
# 検索結果・出典URL・usageも保持する
# ============================================================
def _dump(obj: Any) -> Any:
    from datetime import date, datetime
    from enum import Enum

    from pydantic import BaseModel

    # ------------------------------------------------------------
    # 列挙値を実際の値へ変換する
    # ------------------------------------------------------------
    if isinstance(obj, Enum):
        return _dump(obj.value)

    # ------------------------------------------------------------
    # 文字列・数値・真偽値・Noneはそのまま返す
    # ------------------------------------------------------------
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # ------------------------------------------------------------
    # 日付・時刻を文字列へ変換する
    # ------------------------------------------------------------
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()

    # ------------------------------------------------------------
    # 辞書の各値を再帰的に変換する
    # ------------------------------------------------------------
    if isinstance(obj, dict):
        return {
            key: _dump(value)
            for key, value in obj.items()
        }

    # ------------------------------------------------------------
    # リスト・タプルの各要素を再帰的に変換する
    # ------------------------------------------------------------
    if isinstance(obj, (list, tuple)):
        return [
            _dump(value)
            for value in obj
        ]

    # ------------------------------------------------------------
    # SDKオブジェクトから公開項目と追加項目を取り出す
    # model_dump()は呼び出さない
    # ------------------------------------------------------------
    if isinstance(obj, BaseModel):
        fields = {
            key: value
            for key, value in vars(obj).items()
            if not key.startswith('_')
        }

        extra_fields = getattr(
            obj,
            '__pydantic_extra__',
            None,
        ) or {}

        fields.update(extra_fields)

        return _dump(fields)

    # ------------------------------------------------------------
    # 未対応の型は，情報を捨てず明示的に停止する
    # ------------------------------------------------------------
    raise TypeError(
        'API応答に未対応の型が含まれています：'
        f'{type(obj).__name__}'
    )


# ============================================================
# 有効な出典URLを重複なしで保持する
# ============================================================
def _source(sources: list, title: str, url: str) -> None:
    if safe_url(url) and not any(s['url'] == url for s in sources):
        sources.append({'title': title or url, 'url': url})


# ============================================================
# OpenAI応答から参照URLと，URLを持たない専用データ名を取得する
# 本文の引用URLを優先し，検索結果URLも漏れなく保持する
# ============================================================
def _openai_sources(raw: dict) -> tuple[list, list]:
    sources = []
    api_names = []
    items = raw.get('output') or []

    # ------------------------------------------------------------
    # 本文に付いた引用URLを優先する
    # ------------------------------------------------------------
    for item in items:
        for part in item.get('content') or []:
            for annotation in part.get('annotations') or []:
                if annotation.get('type') == 'url_citation':
                    _source(
                        sources,
                        annotation.get('title') or '',
                        annotation.get('url') or '',
                    )

    # ------------------------------------------------------------
    # 検索結果URLと，天気等の専用データ名を取得する
    # ------------------------------------------------------------
    for item in items:
        if item.get('type') != 'web_search_call':
            continue

        action = item.get('action') or {}

        for source in action.get('sources') or []:
            if not isinstance(source, dict):
                continue

            url = source.get('url') or source.get('uri') or ''

            if safe_url(url):
                _source(sources, source.get('title') or '', url)
            elif source.get('type') == 'api':
                name = source.get('name') or '専用データ'

                if name not in api_names:
                    api_names.append(name)

    return sources, api_names


# ============================================================
# 複数回のAPI利用量を合算する
# 不明なトークン数は0として扱わず，Noneを保持する
# ============================================================
def _sum_usage(usages: list) -> UsageSummary:
    totals = {}

    for key in ('input_tokens', 'output_tokens', 'total_tokens'):
        values = [getattr(usage, key, None) for usage in usages]
        totals[key] = (
            sum(values)
            if values and all(isinstance(value, int) for value in values)
            else None
        )

    return UsageSummary(**totals)


# ============================================================
# 本文料金と検索料金をまとめ，主な参考URL一覧を付ける
# ============================================================
def _finish(result: TextResult, info: dict) -> SearchReply:

    # 無料枠を跨ぐ課金はAPI応答から判定できないため，定価概算と明記する．
    # 不明な検索件数・単価を0円にはしない．
    base = result.cost or estimate_chat_cost_from_usage(model=result.model, usage=result.usage)
    fee = info['estimated_search_usd']
    info['text_usd'] = base.usd if base else None
    info['pricing_date'] = PRICING_DATE
    info['cost_kind'] = '定価概算（無料枠・契約割引は未反映）'
    total = None
    if base is not None and fee is not None:
        total = replace(base, usd=base.usd + fee, jpy=(base.usd + fee) * base.usd_jpy,
                        fx_source='estimate:web_search:' + base.fx_source)
    info['total_usd'] = total.usd if total else None

    # 検索料金不明時は合計costをNoneにし，本文料金を合計と誤記しない．
    # ------------------------------------------------------------
    # APIから取得したURLを回答末尾に必ず一覧表示する
    # モデルが参考URLの記載を省略しても，こちらで補う
    # ------------------------------------------------------------
    answer = result.text.rstrip()

    # 全件はログへ残し，回答の参考URL一覧だけを指定件数へ絞る．
    all_sources = list(info.get('sources') or [])
    # 詳細検索のNoneは件数制限なし．通常検索は最大10件とする．
    source_limit = info.get('source_limit', 10)
    sources = (
        all_sources
        if source_limit is None
        else all_sources[:int(source_limit)]
    )
    info['all_sources'] = all_sources
    info['sources'] = sources
    info['omitted_source_count'] = max(0, len(all_sources) - len(sources))
    info['sources_in_text'] = bool(sources)

    if sources:
        lines = ['**主な参考URL**']

        for number, source in enumerate(sources, 1):
            title = source.get('title') or source['url']
            url = source['url']

            lines.append(f'{number}．{title}\n\n{url}')

        if info['omitted_source_count']:
            lines.append(f"※参考URL一覧は主な{len(sources)}件に絞っています．")

        answer += '\n\n' + '\n\n'.join(lines)

    else:
        answer += '\n\n**参考URL：取得できませんでした．**'

        if info.get('api_sources'):
            names = '，'.join(info['api_sources'])
            answer += (
                f'\n専用データ（{names}）は取得しましたが，'
                'URLを持つ参照ページを確認できませんでした．'
            )
        else:
            answer += '\n検索結果の出典を確認できていません．' 

    return SearchReply(
        replace(
            result,
            text=answer,
            cost=total,
            raw={'web_search': info},
        ),
        info,
    )


# ============================================================
# 通常・詳細の指定に従って検索付き回答を取得する
# ============================================================
def call_text_with_search(*, provider: str, model: str, prompt: str,
                          system: str, max_output_tokens: int,
                          web_search: bool = False, detailed_search: bool = False) -> SearchReply:
    if not web_search:
        return SearchReply(call_text(provider=provider, model=model, prompt=prompt,
                                     system=system, max_output_tokens=max_output_tokens),
                           {'requested': False, 'performed': False, 'sources': []})
    if provider not in ('openai', 'gemini'):
        raise ValueError('このプロバイダーはWeb検索未対応です．OpenAIまたはGeminiを選択してください．')
    source_limit = None if detailed_search else 10

    info = {'requested': True, 'detailed_search': bool(detailed_search),
            'source_limit': source_limit, 'performed': False, 'sources': [], 'queries': [],
            'calls': None, 'estimated_search_usd': None, 'search_suggestions': '',
            'pricing_url': '', 'note': ''}

    # ------------------------------------------------------------
    # 検索時の回答方針：参照先のタイトルとURLを明記する
    # 実際に取得していないURLは生成させない
    # ------------------------------------------------------------
    system += (
        '\n今回の質問について必ずWeb検索を実行し，検索結果を根拠に回答してください．'
        '\n' + (
            '関連する複数の情報源を調べ，相違点や詳細も確認してください．'
            if detailed_search else
            '質問に関連する公開Webページを調べ，信頼できる情報源を優先してください．'
            '同じ事実について検索を繰り返さないでください．'
        )
        + (
            '\n引用する情報源の件数は制限せず，必要な情報源を確認してください．'
            if detailed_search
            else '\n主な情報源は10件程度を目安にしてください．必要なWeb検索は省略しないでください．'
        )
        + '\n本文では根拠を引用し，取得していないURLを推測で作らないでください．'
        '\n参考URL一覧はアプリが別途付けるため，回答末尾にURL一覧を作成しないでください．'
    )

    if provider == 'openai':
        from common_lib.ai.providers.openai.client import get_client
        from common_lib.ai.providers.openai.text_responses_create import _extract_text, _extract_usage
        response = get_client().responses.create(
            model=model, input=[{'role': 'system', 'content': system},
                                {'role': 'user', 'content': prompt}],
            tools=[{
                'type': 'web_search',
                'search_context_size': 'high' if detailed_search else 'medium',
            }],
            tool_choice='required',
            include=['web_search_call.action.sources'], max_output_tokens=max_output_tokens)
        raw = _dump(response)
        responses = [response]
        raw_responses = [raw]
        sources, api_names = _openai_sources(raw)
        info['source_lookup_attempted'] = False
        info['api_sources'] = api_names
        info['response_source_counts'] = [len(sources)]

        # ------------------------------------------------------------
        # 専用データ等にURLが付かない場合だけ，Webページを追加検索する
        # 回答・出典を再生成し，URLを推測で補うことはしない
        # ------------------------------------------------------------
        if not sources:
            info['source_lookup_attempted'] = True
            lookup_system = system + (
                '\n前回の検索では，参照ページのURLが取得できませんでした．'
                '\n今回はURLを持つ公開Webページを実際に検索・参照して回答してください．'
                '\n天気・株価・スポーツ等の専用データだけでは終えず，'
                'その情報を掲載するWebページも検索してください．'
                '\n検索クエリはweather:等の専用データ指定ではなく，'
                '地名・対象名と通常の検索語を使ってください．'
                '\n確認できるWebページがあれば，本文にその引用を付けてください．'
                '\n検索結果にないURLやページ名を作ってはいけません．'
            )

            try:
                lookup_response = get_client().responses.create(
                    model=model,
                    input=[
                        {'role': 'system', 'content': lookup_system},
                        {'role': 'user', 'content': prompt},
                    ],
                    tools=[{
                        'type': 'web_search',
                        'search_context_size': 'high' if detailed_search else 'medium',
                    }],
                    tool_choice='required',
                    include=['web_search_call.action.sources'],
                    max_output_tokens=max_output_tokens,
                )

                # APIが成功した実績は，後続の変換や選別で消さない．
                responses.append(lookup_response)
                lookup_raw = _dump(lookup_response)
                raw_responses.append(lookup_raw)
                lookup_sources, lookup_api_names = _openai_sources(lookup_raw)
                info['response_source_counts'].append(len(lookup_sources))
                info['api_sources'] = list(dict.fromkeys(api_names + lookup_api_names))

                # 出典と回答が対応するよう，URLを取得できた回答を採用する．
                if lookup_sources and (getattr(lookup_response, 'output_text', '') or '').strip():
                    response = lookup_response
                    raw = lookup_raw

            except Exception as exc:
                info['source_lookup_error'] = str(exc)[:500]
                info['note'] += ' URL取得用の追加検索を完了できませんでした．'

        # ------------------------------------------------------------
        # 検索回数は最初の検索と補助検索を合わせて記録する
        # 本文の抽出は採用した応答だけから行う
        # ------------------------------------------------------------
        info['api_request_count'] = len(responses)
        items = [
            item
            for response_raw in raw_responses
            for item in response_raw.get('output') or []
        ]
        calls = [x for x in items if x.get('type') == 'web_search_call']
        completed = [x for x in calls if x.get('status') == 'completed']
        info.update(performed=bool(completed), calls=len(calls),
                    estimated_search_usd=len(calls) * .01,
                    pricing_url='https://developers.openai.com/api/docs/pricing')

        # ------------------------------------------------------------
        # 検索クエリと検索結果URLを取得する
        # 本文に引用情報が付かなかった場合もURLを保持する
        # ------------------------------------------------------------
        search_sources = []

        for item in calls:
            action = item.get('action') or {}

            if action.get('query'):
                info['queries'].append(action['query'])

            for source in action.get('sources') or []:
                if not isinstance(source, dict):
                    continue

                _source(
                    search_sources,
                    source.get('title') or '',
                    source.get('url') or '',
                )

        # API annotationsを出典の正本とする（モデルが生成したURLを信用しない）．
        for item in items:
            for part in item.get('content', []):
                for ann in part.get('annotations', []):
                    if ann.get('type') == 'url_citation':
                        _source(info['sources'], ann.get('title', ''), ann.get('url', ''))

        # 本文の引用先を優先し，検索候補はその後へ追加する．
        for source in search_sources:
            _source(info['sources'], source['title'], source['url'])

        # 本文中の引用範囲へAPIが返したURLを差し込む．
        text_parts = []
        for item in raw.get('output') or []:
            for part in item.get('content', []):
                text = part.get('text')
                if not isinstance(text, str):
                    continue
                markers = []
                for ann in part.get('annotations', []):
                    end, url = ann.get('end_index'), ann.get('url', '')
                    if ann.get('type') == 'url_citation' and isinstance(end, int) and safe_url(url):
                        markers.append((end, f' [出典]({url})'))
                for end, marker in sorted(set(markers), reverse=True):
                    if 0 <= end <= len(text):
                        text = text[:end] + marker + text[end:]
                text_parts.append(text)
        result = TextResult(provider='openai', model=model,
                            text='\n'.join(text_parts) or _extract_text(response),
                            usage=_sum_usage([_extract_usage(item) for item in responses]))
        if raw.get('status') == 'incomplete':
            info['note'] = '出力上限等により回答が途中で終了しました．'
    else:
        from google.genai import types
        from common_lib.ai.providers.gemini.client import configure_gemini
        response = configure_gemini().models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system,
                max_output_tokens=max_output_tokens,
                tools=[types.Tool(google_search=types.GoogleSearch())]))
        raw = _dump(response)
        candidates = raw.get('candidates') or []
        gm = (candidates[0].get('grounding_metadata') or {}) if candidates else {}
        queries = gm.get('web_search_queries') or []
        chunks = gm.get('grounding_chunks') or []
        info.update(performed=bool(queries or chunks), queries=queries,
                    search_suggestions=(gm.get('search_entry_point') or {}).get('rendered_content', ''),
                    pricing_url='https://ai.google.dev/gemini-api/docs/pricing')

        # Gemini 3+ は検索クエリ単位，2.x はgrounded prompt単位．
        if model.startswith(('gemini-3', 'gemini-4')):
            info['calls'] = len(queries) if queries else (None if chunks else 0)
            if info['calls'] is not None:
                info['estimated_search_usd'] = info['calls'] * .014
        elif model.startswith('gemini-2.5'):
            info['calls'] = int(info['performed'])
            info['estimated_search_usd'] = info['calls'] * .035
        for chunk in chunks:
            web = chunk.get('web') or {}
            _source(info['sources'], web.get('title', ''), web.get('uri', ''))

        # grounding_supportsの文字範囲にクリック可能な参照番号を付ける．
        text = response.text or ''
        inserts = []
        for support in gm.get('grounding_supports') or []:
            end = (support.get('segment') or {}).get('end_index')
            refs = []
            for idx in support.get('grounding_chunk_indices') or []:
                if 0 <= idx < len(chunks):
                    web = chunks[idx].get('web') or {}
                    url = web.get('uri', '')
                    if safe_url(url):
                        refs.append(f'[{idx + 1}]({url})')
            if isinstance(end, int) and 0 <= end <= len(text) and refs:
                inserts.append((end, ' ' + ' '.join(refs)))
        for end, marker in sorted(inserts, reverse=True):
            text = text[:end] + marker + text[end:]
        um = raw.get('usage_metadata') or {}
        out = um.get('candidates_token_count')
        thoughts = um.get('thoughts_token_count', 0) or 0
        usage = UsageSummary(input_tokens=um.get('prompt_token_count'),
            output_tokens=out + thoughts if out is not None else None,
            total_tokens=um.get('total_token_count'), raw=um)
        result = TextResult(provider='gemini', model=model, text=text, usage=usage)
        if candidates and candidates[0].get('finish_reason') == 'MAX_TOKENS':
            info['note'] = '出力上限により回答が途中で終了しました．'
    if not info['performed']:
        info['note'] += ' 検索実行を確認できませんでした．検索済みの回答として扱わないでください．'
    return _finish(result, info)
