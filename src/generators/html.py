from jinja2 import Environment, FileSystemLoader
import os
import datetime
from src.utils.common import parse_article_datetime

# Setup Jinja2 env
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

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
        root_path="../.." 
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
        root_path="../..", # doc/members/<Page> -> root is ../..
        active_tab="members",
        now_year=datetime.datetime.now().year,
    )
    return html

def render_member_index(members_list):
    """
    Renders the members index page.
    members_list: list of dict { "name": ..., "filename": ... }
    """
    template = env.get_template("member_index.html")
    html = template.render(
        members=members_list,
        root_path="../..", # doc/members/index.html -> root is ../..
        active_tab="members",
        now_year=datetime.datetime.now().year,
    )
    return html

def render_dashboard(ai_latest, xr_latest, gov_latest, members_latest, section_links=None):
    template = env.get_template("dashboard.html")
    return template.render(
        ai_latest=ai_latest,
        xr_latest=xr_latest,
        gov_latest=gov_latest,
        members_latest=members_latest,
        section_links=section_links or {},
        now_year=datetime.datetime.now().year,
        active_tab="home",
        root_path="."
    )
