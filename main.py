import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

SERVERCHAN_KEY = os.environ.get('SERVERCHAN_KEY', '')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

AI_KEYWORDS = [
    'llm', 'gpt', 'chatgpt', 'claude', 'gemini', 'ai', 'machine learning',
    'deep learning', 'neural', 'diffusion', 'transformer', 'agent', 'rag',
    'embedding', 'vector', 'langchain', 'inference', 'fine-tun', 'multimodal',
    'language model', 'generative', 'openai', 'anthropic', 'ollama',
    'stable diffusion', 'copilot', 'vision model', 'mcp', 'vllm', 'lora',
]


def is_ai_related(text):
    t = text.lower()
    return any(kw in t for kw in AI_KEYWORDS)


def get_trending_ai_repos():
    """抓取 GitHub Trending，筛选 AI 相关项目"""
    url = 'https://github.com/trending?since=daily'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f'[Trending] 请求失败: {e}')
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    repos = []

    for article in soup.select('article.Box-row'):
        name_tag = article.select_one('h2 a')
        if not name_tag:
            continue
        full_name = name_tag.get('href', '').strip('/')
        desc_tag = article.select_one('p')
        description = desc_tag.get_text(strip=True) if desc_tag else ''
        lang_tag = article.select_one('[itemprop="programmingLanguage"]')
        language = lang_tag.get_text(strip=True) if lang_tag else ''
        stars_tag = article.select_one('a[href$="/stargazers"]')
        try:
            stars = int(stars_tag.get_text(strip=True).replace(',', '').replace('k', '00')) if stars_tag else 0
        except ValueError:
            stars = 0
        today_tag = article.select_one('span.d-inline-block.float-sm-right')
        today_stars = today_tag.get_text(strip=True) if today_tag else ''

        if is_ai_related(full_name + ' ' + description):
            repos.append({
                'name': full_name,
                'description': description,
                'language': language,
                'stars': stars,
                'today_stars': today_stars,
                'url': f'https://github.com/{full_name}',
            })

    return repos[:8]


def get_new_fast_growing_repos():
    """GitHub Search API：近14天创建、Star 快速增长的 AI 项目"""
    since = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    queries = [
        f'created:>{since} stars:>30 topic:llm',
        f'created:>{since} stars:>30 topic:ai-agent',
        f'created:>{since} stars:>30 topic:large-language-model',
        f'created:>{since} stars:>50 topic:machine-learning',
    ]

    headers = {'Accept': 'application/vnd.github+json'}
    if GITHUB_TOKEN:
        headers['Authorization'] = f'Bearer {GITHUB_TOKEN}'

    seen = set()
    repos = []

    for query in queries:
        url = (
            'https://api.github.com/search/repositories'
            f'?q={requests.utils.quote(query)}&sort=stars&order=desc&per_page=6'
        )
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 403:
                print('[Search API] 触达速率限制，跳过')
                break
            resp.raise_for_status()
        except Exception as e:
            print(f'[Search API] 请求失败: {e}')
            continue

        for item in resp.json().get('items', []):
            if item['full_name'] not in seen:
                seen.add(item['full_name'])
                repos.append({
                    'name': item['full_name'],
                    'description': item.get('description') or '',
                    'language': item.get('language') or '',
                    'stars': item['stargazers_count'],
                    'created_at': item['created_at'][:10],
                    'url': item['html_url'],
                })

    repos.sort(key=lambda x: x['stars'], reverse=True)
    return repos[:8]


def format_message(trending, new_repos):
    today = datetime.now().strftime('%Y-%m-%d')
    lines = [f'# AI雷达日报 {today}', '']

    lines += ['## 🔥 今日 GitHub AI 趋势榜', '']
    if trending:
        for i, r in enumerate(trending, 1):
            stars_info = f'  `{r["today_stars"]}`' if r['today_stars'] else ''
            lang_info = f'  `{r["language"]}`' if r['language'] else ''
            lines.append(f'**{i}. [{r["name"]}]({r["url"]})**{lang_info}{stars_info}')
            if r['description']:
                lines.append(f'> {r["description"][:120]}')
            lines.append('')
    else:
        lines += ['暂无数据（可能是网络问题）', '']

    lines += ['## 🚀 近两周新冒头的 AI 项目', '']
    if new_repos:
        for i, r in enumerate(new_repos, 1):
            lines.append(f'**{i}. [{r["name"]}]({r["url"]})** ⭐ {r["stars"]:,}')
            lines.append(f'创建于 {r["created_at"]}  `{r["language"]}`')
            if r['description']:
                lines.append(f'> {r["description"][:120]}')
            lines.append('')
    else:
        lines += ['暂无数据', '']

    return '\n'.join(lines)


def send_to_wechat(title, content):
    if not SERVERCHAN_KEY:
        print('⚠️  未设置 SERVERCHAN_KEY，本次仅打印预览')
        print('=' * 60)
        print(content)
        print('=' * 60)
        return

    url = f'https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send'
    try:
        resp = requests.post(url, data={'title': title, 'desp': content}, timeout=15)
        result = resp.json()
        if result.get('code') == 0:
            print('✅ 微信推送成功')
        else:
            print(f'❌ 推送失败: {result}')
    except Exception as e:
        print(f'❌ 推送异常: {e}')


if __name__ == '__main__':
    print('🔍 正在获取 GitHub Trending AI 项目...')
    trending = get_trending_ai_repos()
    print(f'   找到 {len(trending)} 个趋势项目')

    print('🔍 正在搜索近两周新冒头的 AI 项目...')
    new_repos = get_new_fast_growing_repos()
    print(f'   找到 {len(new_repos)} 个新项目')

    content = format_message(trending, new_repos)
    today = datetime.now().strftime('%m/%d')
    total = len(trending) + len(new_repos)
    send_to_wechat(f'AI雷达 {today} | 精选 {total} 个项目', content)
