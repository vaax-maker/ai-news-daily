from jinja2 import Environment, FileSystemLoader
import os
import datetime
from src.utils.common import parse_article_datetime

# Setup Jinja2 env
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

# Inject GA ID globally
env.globals["ga_id"] = os.environ.get("GOOGLE_ANALYTICS_ID", "")

# Custom Tests
def containing(value, search):
    return search in value

env.tests["containing"] = containing

def render_daily_page(articles, date_str, time_str, config, active_tab="home"):
    sorted_articles = sorted(articles, key=parse_article_datetime, reverse=True)

    if config.is_table_view:
        template = env.get_template("daily_table.html")
    else:
        template = env.get_template("daily_list.html")

    return template.render(
        articles=sorted_articles,
        date_str=date_str,
        time_str=time_str,
        category_display_name=config.display_name,
        active_tab=config.key,
        now_year=datetime.datetime.now().year,
        config=config,
        root_path="../..",
        now_timestamp=datetime.datetime.now().timestamp() 
    )

def render_archive_index(run_entries, config):
    template = env.get_template("archive_index.html")
    return template.render(
        run_entries=run_entries,
        category_display_name=config.display_name,
        active_tab=config.key,
        category_key=config.key,
        now_year=datetime.datetime.now().year,
        root_path=".."
    )


def render_gov_archive(announcements):
    template = env.get_template("gov_archive.html")
    return template.render(
        announcements=announcements,
        active_tab="gov",
        now_year=datetime.datetime.now().year,
        now=datetime.datetime.now(),  # 현재 시간 전달
        root_path="..",
    )



def render_member_page(member, articles, now_str):
    """
    Renders the individual member page with their entire history.
    """
    template = env.get_template("member_page.html")
    html = template.render(
        member=member,
        articles=articles,
        updated_date=now_str,
        root_path="..",  # docs/members/<Page> -> root is ..
        active_tab="members",
        now_year=datetime.datetime.now().year,
    )
    return html

def render_member_index(members_list, all_news=None, profiles=None):
    """
    Renders the members index page.
    members_list: list of dict { "name": ..., "filename": ... }
    all_news: list of all member news articles for the grid display
    profiles: dict of company profiles for the profile tab
    """
    template = env.get_template("member_index.html")
    html = template.render(
        members=members_list,
        all_news=all_news or [],
        profiles=profiles or {},
        root_path="..",  # docs/members/index.html -> root is ..
        active_tab="members",
        now_year=datetime.datetime.now().year,
    )
    return html

def render_dashboard(ai_latest, xr_latest, gov_latest, quickview_latest=None, members_latest=None, section_links=None, last_updated=None):
    from src.utils.common import get_kst_now
    template = env.get_template("dashboard.html")
    return template.render(
        ai_latest=ai_latest,
        xr_latest=xr_latest,
        gov_latest=gov_latest,
        quickview_latest=quickview_latest or [],
        section_links=section_links or {},
        last_updated=last_updated or get_kst_now().strftime("%Y년 %m월 %d일 %H시 %M분"),
        now_year=datetime.datetime.now().year,
        active_tab="home",
        root_path="."
    )


def render_board_page():
    template = env.get_template("board.html")
    return template.render(
        active_tab="board",
        now_year=datetime.datetime.now().year,
        root_path=".." # docs/board/index.html -> root is ..
    )

def render_mobile_landing(ai_items, xr_items, gov_items, links=None):
    """
    Renders the mobile-optimized daily briefing landing page.
    """
    if links is None: links = {}
    
    template = env.get_template("mobile_landing.html")
    from src.utils.common import get_kst_now
    now = get_kst_now()
    weekday_map = {0:'월', 1:'화', 2:'수', 3:'목', 4:'금', 5:'토', 6:'일'}
    wd = weekday_map[now.weekday()]
    
    # Match telegram message format: "01/04(토) 20:23"
    date_str = f"{now.strftime('%m/%d')}({wd}) {now.strftime('%H:%M')}"
    
    return template.render(
        ai_items=ai_items,
        xr_items=xr_items,
        gov_items=gov_items,
        links=links,
        date_str=date_str,
        now_year=now.year,
        active_tab="home",
        root_path=".", # docs/briefing.html -> root is .
        now_timestamp=now.timestamp() # For NEW badge logic
    )
def render_admin_page():
    """
    Renders the admin notifier panel.
    """
    template = env.get_template("admin.html")
    return template.render(
        active_tab="home",
        now_year=datetime.datetime.now().year,
        root_path=".", # docs/admin.html -> root is .
    )

def render_quickview_index(pages):
    """
    Renders the quickview index page with list of all quickview pages.
    pages: list of dict { "id": ..., "title": ..., "created_at": ..., "created_display": ..., "is_new": ... }
    """
    template = env.get_template("quickview_index.html")
    return template.render(
        pages=pages,
        active_tab="quickview",
        now_year=datetime.datetime.now().year,
        root_path=".."  # docs/quickview/index.html -> root is ..
    )

def render_quickview_page(title, content, created_display, page_url="", created_at=0):
    """
    Renders an individual quickview page with the provided HTML content.
    """
    template = env.get_template("quickview_page.html")
    return template.render(
        title=title,
        content=content,
        created_display=created_display,
        created_at=created_at,
        page_url=page_url,
        active_tab="quickview",
        now_year=datetime.datetime.now().year,
        root_path=".."  # docs/quickview/page.html -> root is ..
    )


def render_daily_briefing(
    key_message: str,
    morning_ai: list,
    morning_xr: list,
    afternoon_ai: list,
    afternoon_xr: list,
    date_display: str,
    gov_items: list = None,
    root_path: str = "..",
    wordcloud_image: str = None
):
    """
    Renders the daily briefing page with Key Message, AI/XR articles, and Gov projects.
    
    Args:
        key_message: HTML formatted 3-line Key Message
        morning_ai: AI articles from 8AM run
        morning_xr: XR articles from 8AM run
        afternoon_ai: AI articles from 4PM run
        afternoon_xr: XR articles from 4PM run
        date_display: Display date string (e.g., "2026년 01월 11일")
        gov_items: List of government announcements
        root_path: Relative path to docs root (default ".." for docs/briefing/)
        wordcloud_image: Relative path to wordcloud image (optional)
    """
    if gov_items is None:
        gov_items = []
        
    template = env.get_template("briefing_daily.html")
    return template.render(
        key_message=key_message,
        morning_ai=morning_ai,
        morning_xr=morning_xr,
        afternoon_ai=afternoon_ai,
        afternoon_xr=afternoon_xr,
        gov_items=gov_items,
        date_display=date_display,
        now_year=datetime.datetime.now().year,
        root_path=root_path,
        wordcloud_image=wordcloud_image
    )


def render_briefing_archive(entries: list):
    """
    Renders the briefing archive index page.
    
    Args:
        entries: List of dict { "filename": ..., "date_str": ..., "date_display": ... }
    """
    template = env.get_template("briefing_archive.html")
    return template.render(
        entries=entries,
        now_year=datetime.datetime.now().year,
        root_path=".."  # docs/briefing/index.html -> root is ..
    )

def render_guide_page():
    """
    Renders the service guide page.
    """
    template = env.get_template("guide.html")
    return template.render(
        active_tab="guide",
        now_year=datetime.datetime.now().year,
        root_path="."  # docs/guide.html -> root is .
    )
