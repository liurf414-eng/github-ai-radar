import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

SERVERCHAN_KEY = os.environ.get('SERVERCHAN_KEY', '')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')

AI_KEYWORDS = [
    'llm', 'gpt', 'chatgpt', 'claude', 'gemini', 'ai', 'machine learning',
    'deep learning', 'neural', 'diffusion', 'transformer', 'agent', 'rag',
    'embedding', 'vector', 'langchain', 'inference', 'fine-tun', 'multimodal',
    'language model', 'generative', 'openai', 'anthropic', 'ollama',
    'stable diffusion', 'copilot', 'vision model', 'mcp', 'vllm', 'lora',
]


def generate_summary(name, description):
    """调用 DeepSeek API 生成三行中文摘要"""
    if not DEEPSEEK_API_KEY:
        return None
    prompt = (
        f'GitHub项目名：{name}\n'
        f'官方描述：{description or "无"}\n\n'
        '请用中文简洁回答以下三个问题，每个问题一句话，直接输出三行，不加编号和标题：\n'
        '1. 这个项目是干嘛的？\n'
        '2. 适合谁用？\n'
        '3. 为什么最近火了？'
    )
    try:
        resp = requests.post(
            'https://api.deepseek.com/chat/completions',
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'deepseek-chat',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 200,
                'temperature': 0.3,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f'[DeepSeek] {name} 摘要生成失败: {e}')
        return None


def is_ai_related(text):
    t = text.lower()
    return any(kw in t for kw in AI_KEYWORDS)


def scrape_trending(ai_only=True):
    """抓取 GitHub Trending，ai_only=True 时只返回 AI 相关项目"""
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

        if ai_only and not is_ai_related(full_name + ' ' + description):
            continue

        repos.append({
            'name': full_name,
            'description': description,
            'language': language,
            'stars': stars,
            'today_stars': today_stars,
            'url': f'https://github.com/{full_name}',
        })

    return repos


def get_trending_ai_repos():
    return scrape_trending(ai_only=True)[:8]


def get_trending_all_repos():
    return scrape_trending(ai_only=False)[:10]


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


def format_repo_block(r, index, show_created=False):
    """生成单个项目的展示块，包含 AI 摘要"""
    lines = []

    # 第一行：项目名（单独一行）
    lines.append(f'**{index}. [{r["name"]}]({r["url"]})**')

    # 第二行：语言 · 星星（单独一行）
    parts = []
    if r.get('language'):
        parts.append(f'`{r["language"]}`')
    if show_created:
        parts.append(f'创建于 {r["created_at"]}')
        parts.append(f'⭐ {r["stars"]:,}')
    elif r.get('today_stars'):
        parts.append(f'今日 ⭐ {r["today_stars"]}')
    if parts:
        lines.append(' · '.join(parts))

    lines.append('')  # 空行，摘要前留呼吸感

    # 摘要：每条单独一行，行间留空
    summary = generate_summary(r['name'], r.get('description', ''))
    time.sleep(0.5)

    if summary:
        summary_lines = summary.strip().splitlines()
        labels = ['📌 是什么', '👤 适合谁', '🔥 为何火']
        for label, line in zip(labels, summary_lines):
            if line.strip():
                lines.append(f'{label}：{line.strip()}')
                lines.append('')
    elif r.get('description'):
        lines.append(f'> {r["description"][:120]}')
        lines.append('')

    lines.append('---')  # 项目间分隔线
    lines.append('')
    return lines


def format_trending_simple(repos):
    """全站趋势榜：简洁展示，不生成 AI 摘要"""
    lines = []
    for i, r in enumerate(repos, 1):
        lang_info = f'`{r["language"]}` · ' if r.get('language') else ''
        stars_info = f'今日 ⭐ {r["today_stars"]}' if r.get('today_stars') else ''
        lines.append(f'**{i}. [{r["name"]}]({r["url"]})**')
        lines.append(f'{lang_info}{stars_info}')
        if r.get('description'):
            lines.append(f'> {r["description"][:80]}')
        lines.append('')
    return lines


def format_message(trending, new_repos, all_trending):
    today = datetime.now().strftime('%Y-%m-%d')
    lines = [f'# AI雷达日报 {today}', '']

    lines += ['## 🔥 今日 GitHub AI 趋势榜', '']
    if trending:
        for i, r in enumerate(trending, 1):
            lines += format_repo_block(r, i)
    else:
        lines += ['暂无数据（可能是网络问题）', '']

    lines += ['## 🚀 近两周新冒头的 AI 项目', '']
    if new_repos:
        for i, r in enumerate(new_repos, 1):
            lines += format_repo_block(r, i, show_created=True)
    else:
        lines += ['暂无数据', '']

    lines += ['## 🌐 GitHub 今日全站热榜 Top 10', '']
    if all_trending:
        for i, r in enumerate(all_trending, 1):
            lines += format_repo_block(r, i)
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

    print('🔍 正在获取 GitHub 全站趋势榜...')
    all_trending = get_trending_all_repos()
    print(f'   找到 {len(all_trending)} 个全站趋势项目')

    content = format_message(trending, new_repos, all_trending)
    today = datetime.now().strftime('%m/%d')
    total = len(trending) + len(new_repos)
    send_to_wechat(f'AI雷达 {today} | 精选 {total} 个项目', content)
