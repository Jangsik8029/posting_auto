"""posting_auto + cafe_crawler 통합 CLI.

서브커맨드:
  publish          ChatGPT 로 글 생성 → WordPress 발행 (기존 main 동작)
  reoptimize       기존 WP 글의 네이버 SEO 재최적화
  collect          외부 사이트를 스크랩해 knowledge.db 에 적재

  crawl            네이버/다음 카페에서 키워드 검색 결과 수집
  topics           수집된 검색 결과에서 블로그 토픽 후보 추출
  report           CSV/Excel/Markdown 리포트 생성
  searches         과거 검색 이력 표시
  export-kb        카페 게시글을 knowledge.db 로 export
  post-from-cafe   토픽 후보 1개 → publish 호출 (전체 파이프라인)
"""

import argparse
import logging
import os
import sys
from types import SimpleNamespace

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.table import Table

from blogbot.clients.openai_client import list_prompt_folders
from blogbot.config import AppConfig
from blogbot.integrations.knowledge_collector import collect_from_site
from blogbot.integrations.knowledge_db import upsert_knowledge_items
from blogbot.workflows.publish import publish_post
from blogbot.workflows.rewrite_seo import reoptimize_post_naver_seo

from cafe_crawler.analyzer import score_posts
from cafe_crawler.collectors import search_daum_cafe, search_naver_cafe
from cafe_crawler.config import KNOWLEDGE_DB_PATH
from cafe_crawler.storage import (
    create_search,
    fetch_posts,
    is_already_published,
    latest_search_id,
    list_searches,
    record_publication,
    save_posts,
    update_post_scores,
)
from cafe_crawler.storage.exporter import export_csv, export_excel, export_markdown
from cafe_crawler.workflows import (
    export_to_knowledge_db,
    post_from_cafe,
    select_topics,
)

console = Console()
log = logging.getLogger("posting_auto")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


# --------------------------------------------------------------------------- #
# 기존 publish / reoptimize / collect
# --------------------------------------------------------------------------- #


def _config_defaults_namespace() -> SimpleNamespace:
    return SimpleNamespace(
        topic="", main_topic="", sub_topics="", prompt_folder="",
        image_count=4, submit_search=False, sitemap_url="",
        knowledge_db_path="data/knowledge.db", knowledge_keyword="",
        collect_url="", collect_only=False,
        status="draft", with_image=False, image_source="pixabay",
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_api_key=None, wp_domain=None, wp_user=None,
        wp_app_password=None, pixabay_api_key=None,
    )


def _config_from(args: argparse.Namespace) -> AppConfig:
    base = _config_defaults_namespace()
    for key, val in vars(args).items():
        setattr(base, key, val)
    return AppConfig.from_args(base)


def cmd_publish(args: argparse.Namespace) -> int:
    config = _config_from(args)
    if not config.topic.strip():
        console.print("[red]--topic 이 필요합니다.[/]")
        return 1
    if not config.prompt_folder.strip():
        available = list_prompt_folders()
        console.print(
            "[red]--prompt-folder 가 필요합니다.[/] "
            f"사용 가능: {available if available else '(없음)'}"
        )
        return 1
    config.validate("publish")

    print(f"Topic: {config.topic}")
    print(f"Main topic: {config.main_topic}")
    print(f"Sub topics: {', '.join(config.sub_topics) if config.sub_topics else '(none)'}")
    print(f"Prompt folder: {config.prompt_folder}")
    print(f"Model: {config.model}")
    print("Running publish workflow...")
    result = publish_post(config)

    print("Post created successfully.")
    print(f"Post ID: {result['post_id']}")
    print(f"Link: {result['public_url']}")
    print(f"Pretty Link: {result['pretty_url']}")
    print(f"Edit URL: {result['edit_url']}")
    print(f"Generated title: {result['title']}")
    print(f"SEO keyword: {result['seo_keyword']}")
    print(f"Reference count: {result['reference_count']}")
    if config.knowledge_keyword:
        print(f"Knowledge keyword used: {config.knowledge_keyword}")
    if config.with_image:
        if result["image_url"]:
            print(f"Image uploaded count: {result['image_count_uploaded']}")
            print(f"Image uploaded URLs: {result['image_url']}")
            print(f"Image sources: {result['image_source']}")
        else:
            print(f"Image status: {result['image_status']}")
            if result["image_message"]:
                print(f"Image detail: {result['image_message']}")
    if config.submit_search:
        print(f"Search submit result: {result['search_submit']}")
    if config.status != "publish":
        print("Note: draft/private posts are not public URLs.")
    return 0


def cmd_reoptimize(args: argparse.Namespace) -> int:
    config = _config_from(args)
    config.validate("reoptimize")
    print(f"Re-optimizing WordPress post ID {args.post_id} for Naver SEO...")
    result = reoptimize_post_naver_seo(
        domain=config.wp_domain,
        wp_user=config.wp_user,
        wp_app_password=config.wp_app_password,
        post_id=args.post_id,
    )
    print("Post updated for Naver SEO.")
    print(f"Post ID: {result['post_id']}")
    print(f"Title: {result['title']}")
    print(f"Excerpt preview: {result['excerpt_preview']}")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    args_with_collect = argparse.Namespace(**vars(args))
    args_with_collect.collect_url = args.url
    args_with_collect.collect_only = True
    config = _config_from(args_with_collect)
    config.validate("collect")

    print(f"Collecting site data: {config.collect_url}")
    collected = collect_from_site(config.collect_url, max_pages=args.max_pages)
    saved = upsert_knowledge_items(config.knowledge_db_path, collected)
    print(f"Collected items: {len(collected)}")
    if collected:
        preview = " | ".join(x.link for x in collected[:3])
        print(f"Collected links preview: {preview}")
    else:
        print("No pages were collected. The target site may be JS-rendered or blocked.")
    print(f"Saved to DB: {config.knowledge_db_path} ({saved} upserted)")
    return 0


# --------------------------------------------------------------------------- #
# cafe_crawler 신규 서브커맨드
# --------------------------------------------------------------------------- #


def cmd_crawl(args: argparse.Namespace) -> int:
    query: str = args.query
    do_naver = not args.daum_only
    do_daum = not args.naver_only

    search_id = create_search(query)
    console.print(f"[bold cyan]검색 #{search_id}[/] '{query}' 시작")

    collected: list[dict] = []
    naver_count = daum_count = 0

    if do_naver:
        try:
            for post in search_naver_cafe(query, max_pages=args.max_pages, sort=args.sort):
                collected.append(post)
                naver_count += 1
            console.print(f"  네이버 카페: {naver_count}건")
        except Exception as e:
            log.error("네이버 수집 실패: %s", e)
            if not args.continue_on_error:
                return 1

    if do_daum:
        daum_sort = "recency" if args.sort == "date" else "accuracy"
        try:
            for post in search_daum_cafe(query, max_pages=args.max_pages, sort=daum_sort):
                collected.append(post)
                daum_count += 1
            console.print(f"  다음 카페: {daum_count}건")
        except Exception as e:
            log.error("다음 수집 실패: %s", e)
            if not args.continue_on_error:
                return 1

    if not collected:
        console.print("[yellow]수집된 게시글이 없습니다.[/]")
        return 0

    scored = score_posts(collected)
    saved = save_posts(search_id, scored)
    console.print(f"[green]저장 완료:[/] {saved}건 (search_id={search_id})")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    sid = _resolve_search_id(args)
    if sid is None:
        console.print("[red]검색 이력이 없습니다. 먼저 'crawl' 을 실행하세요.[/]")
        return 1

    posts = fetch_posts(sid)
    if not posts:
        console.print(f"[yellow]search_id={sid} 에 게시글이 없습니다.[/]")
        return 1

    if args.rescore:
        rescored = score_posts([dict(p) for p in posts])
        update_post_scores({p["id"]: r["score"] for p, r in zip(posts, rescored)})
        console.print("점수 재계산 완료")

    md = export_markdown(sid, top_n=args.top)
    csv = export_csv(sid)
    xlsx = export_excel(sid)

    table = Table(title=f"리포트 생성 (search_id={sid})")
    table.add_column("형식")
    table.add_column("경로")
    table.add_row("Markdown", str(md))
    table.add_row("CSV", str(csv))
    table.add_row("Excel", str(xlsx))
    console.print(table)
    return 0


def _resolve_search_id(args: argparse.Namespace) -> int | None:
    if getattr(args, "search_id", None) is not None:
        return args.search_id
    if getattr(args, "query", None):
        return latest_search_id(args.query)
    return None


def cmd_topics(args: argparse.Namespace) -> int:
    sid = _resolve_search_id(args)
    if sid is None:
        console.print("[red]검색 이력이 없습니다. 먼저 'crawl' 을 실행하세요.[/]")
        return 1
    candidates = select_topics(sid, top=args.top)
    if not candidates:
        console.print("[yellow]토픽 후보를 추출하지 못했습니다.[/]")
        return 1

    table = Table(title=f"토픽 후보 (search_id={sid})")
    table.add_column("#", justify="right")
    table.add_column("main_topic")
    table.add_column("sub_topics")
    table.add_column("대표 카페")
    table.add_column("점수", justify="right")
    table.add_column("URL")
    for c in candidates:
        score = c.metadata.get("score")
        score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
        table.add_row(
            str(c.rank),
            c.main_topic,
            ", ".join(c.sub_topics),
            (c.metadata.get("cafe_name") or "")[:24],
            score_str,
            c.representative_post_url,
        )
    console.print(table)
    return 0


def cmd_searches(args: argparse.Namespace) -> int:
    rows = list_searches(limit=args.limit)
    if not rows:
        console.print("[yellow]저장된 검색 이력이 없습니다.[/]")
        return 0
    table = Table(title="검색 이력")
    table.add_column("ID", justify="right")
    table.add_column("Query")
    table.add_column("실행 시각")
    table.add_column("게시글 수", justify="right")
    for r in rows:
        table.add_row(str(r["id"]), r["query"], r["run_at"], str(r["post_count"]))
    console.print(table)
    return 0


def cmd_export_kb(args: argparse.Namespace) -> int:
    sid = _resolve_search_id(args)
    if sid is None:
        console.print("[red]검색 이력이 없습니다. 먼저 'crawl' 을 실행하세요.[/]")
        return 1
    n = export_to_knowledge_db(sid, knowledge_db_path=KNOWLEDGE_DB_PATH, max_items=args.max)
    console.print(f"[green]export 완료:[/] {n}건 → {KNOWLEDGE_DB_PATH}")
    return 0


def cmd_post_from_cafe(args: argparse.Namespace) -> int:
    sid = _resolve_search_id(args)
    if sid is None:
        console.print("[red]검색 이력이 없습니다. 먼저 'crawl' 을 실행하세요.[/]")
        return 1

    candidates = select_topics(sid, top=max(args.rank, 5))
    if not candidates or args.rank < 1 or args.rank > len(candidates):
        console.print(f"[red]rank={args.rank} 후보가 없습니다 (가능 범위: 1..{len(candidates)}).[/]")
        return 1
    candidate = candidates[args.rank - 1]

    if not args.force and is_already_published(sid, candidate.main_topic, args.prompt_folder):
        console.print(
            f"[yellow]이미 발행됨:[/] search_id={sid}, main_topic='{candidate.main_topic}', "
            f"prompt_folder='{args.prompt_folder}'. 다시 발행하려면 --force 사용."
        )
        return 1

    if not args.skip_export_kb:
        n = export_to_knowledge_db(sid, knowledge_db_path=KNOWLEDGE_DB_PATH)
        console.print(f"  knowledge.db export: {n}건")

    if args.dry_run:
        console.print("[cyan]DRY RUN[/] post-from-cafe 입력 미리보기:")
        preview = {
            "topic": candidate.main_topic,
            "main_topic": candidate.main_topic,
            "sub_topics": candidate.sub_topics,
            "prompt_folder": args.prompt_folder,
            "knowledge_keyword": candidate.source_keyword,
            "status": args.status,
            "with_image": args.with_image,
            "image_source": args.image_source if args.with_image else "(unused)",
            "model": args.model,
        }
        for k, v in preview.items():
            console.print(f"  {k} = {v!r}")
        console.print(
            "[dim]실제 실행 시 AppConfig.from_args 가 OPENAI_API_KEY/WP 자격증명을 .env 에서 읽어옵니다.[/]"
        )
        return 0

    console.print(
        f"[bold]post_from_cafe 실행 중[/] (rank={candidate.rank}, "
        f"main_topic='{candidate.main_topic}')"
    )
    result = post_from_cafe(
        candidate=candidate,
        prompt_folder=args.prompt_folder,
        status=args.status,
        with_image=args.with_image,
        image_source=args.image_source,
        model=args.model,
    )

    if result.publish_result is None:
        console.print("[red]발행 결과 없음[/]")
        return 1
    pr = result.publish_result
    console.print(f"[green]발행 완료[/] post_id={pr['post_id']}, link={pr['public_url']}")

    record_publication(
        search_id=sid,
        candidate_rank=candidate.rank,
        main_topic=candidate.main_topic,
        sub_topics=candidate.sub_topics,
        prompt_folder=args.prompt_folder,
        wp_post_id=pr["post_id"],
        wp_link=pr["public_url"],
        status=args.status,
    )
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #


def _add_publish_args(p: argparse.ArgumentParser) -> None:
    """publish 관련 공통 인자."""
    p.add_argument("--topic", default="", help="Topic")
    p.add_argument("--main-topic", default="", help="Main topic. Defaults to --topic")
    p.add_argument("--sub-topics", default="", help="Comma-separated sub topics")
    p.add_argument("--prompt-folder", default="", help="Prompt folder under blogbot/prompt/")
    p.add_argument("--image-count", type=int, default=4)
    p.add_argument("--submit-search", action="store_true")
    p.add_argument("--sitemap-url", default="")
    p.add_argument("--knowledge-db-path", default="data/knowledge.db")
    p.add_argument("--knowledge-keyword", default="")
    p.add_argument("--status", default="draft", choices=["draft", "publish", "private"])
    p.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    p.add_argument("--openai-api-key")
    p.add_argument("--wp-domain")
    p.add_argument("--wp-user")
    p.add_argument("--wp-app-password")
    p.add_argument("--with-image", action="store_true")
    p.add_argument(
        "--image-source",
        choices=["local", "title", "dalle", "pixabay"],
        default="pixabay",
    )
    p.add_argument("--pixabay-api-key")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="posting_auto",
        description="ChatGPT 글 생성 + WordPress 발행 + 카페 인기글 크롤러 통합 CLI",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # publish (기존 main 동작)
    p_pub = sub.add_parser("publish", help="ChatGPT 로 글 생성 후 WordPress 발행")
    _add_publish_args(p_pub)
    p_pub.set_defaults(func=cmd_publish)

    # reoptimize
    p_re = sub.add_parser("reoptimize", help="기존 WP 글 네이버 SEO 재최적화")
    p_re.add_argument("--post-id", type=int, required=True)
    p_re.add_argument("--wp-domain")
    p_re.add_argument("--wp-user")
    p_re.add_argument("--wp-app-password")
    p_re.add_argument("--openai-api-key")
    p_re.set_defaults(func=cmd_reoptimize)

    # collect
    p_col = sub.add_parser("collect", help="외부 사이트 스크랩 → knowledge.db")
    p_col.add_argument("--url", required=True)
    p_col.add_argument("--max-pages", type=int, default=10)
    p_col.add_argument("--knowledge-db-path", default="data/knowledge.db")
    p_col.add_argument("--openai-api-key")
    p_col.set_defaults(func=cmd_collect)

    # crawl
    p_crawl = sub.add_parser("crawl", help="네이버/다음 카페 인기 게시글 수집")
    p_crawl.add_argument("query", help="검색 키워드")
    p_crawl.add_argument("--max-pages", type=int, default=10)
    p_crawl.add_argument("--sort", choices=["sim", "date"], default="sim")
    p_crawl.add_argument("--naver-only", action="store_true")
    p_crawl.add_argument("--daum-only", action="store_true")
    p_crawl.add_argument("--continue-on-error", action="store_true")
    p_crawl.set_defaults(func=cmd_crawl)

    # topics
    p_top = sub.add_parser("topics", help="토픽 후보 추출")
    p_top.add_argument("query", nargs="?", help="키워드 (생략 시 --search-id 필수)")
    p_top.add_argument("--search-id", type=int)
    p_top.add_argument("--top", type=int, default=5)
    p_top.set_defaults(func=cmd_topics)

    # report
    p_rep = sub.add_parser("report", help="리포트 생성 (Markdown/CSV/Excel)")
    p_rep.add_argument("query", nargs="?")
    p_rep.add_argument("--search-id", type=int)
    p_rep.add_argument("--top", type=int, default=20)
    p_rep.add_argument("--rescore", action="store_true")
    p_rep.set_defaults(func=cmd_report)

    # searches
    p_sea = sub.add_parser("searches", help="과거 검색 이력 표시")
    p_sea.add_argument("--limit", type=int, default=50)
    p_sea.set_defaults(func=cmd_searches)

    # export-kb
    p_kb = sub.add_parser("export-kb", help="카페 게시글 → knowledge.db 적재")
    p_kb.add_argument("query", nargs="?")
    p_kb.add_argument("--search-id", type=int)
    p_kb.add_argument("--max", type=int, default=200)
    p_kb.set_defaults(func=cmd_export_kb)

    # post-from-cafe
    p_pfc = sub.add_parser("post-from-cafe", help="토픽 후보 → publish 자동 호출")
    p_pfc.add_argument("query", nargs="?")
    p_pfc.add_argument("--search-id", type=int)
    p_pfc.add_argument("--rank", type=int, default=1, help="topics 의 몇 번째 후보")
    p_pfc.add_argument("--prompt-folder", required=True)
    p_pfc.add_argument("--status", choices=["draft", "publish", "private"], default="draft")
    p_pfc.add_argument("--with-image", action="store_true")
    p_pfc.add_argument(
        "--image-source",
        choices=["pixabay", "dalle", "local", "title"],
        default="pixabay",
    )
    p_pfc.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    p_pfc.add_argument("--skip-export-kb", action="store_true")
    p_pfc.add_argument("--force", action="store_true")
    p_pfc.add_argument("--dry-run", action="store_true")
    p_pfc.set_defaults(func=cmd_post_from_cafe)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
