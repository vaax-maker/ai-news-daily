from jinja2 import Environment, FileSystemLoader
import os
import datetime

# Setup Jinja2 env
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

def render_daily_page(articles, date_str, time_str, config, active_tab="home"):
    if config.is_table_view:
        template = env.get_template("daily_table.html")
    else:
        template = env.get_template("daily_list.html")
        
    return template.render(
        articles=articles,
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
        now_year=datetime.datetime.now().year,
        root_path=".."
    )

def render_dashboard(categories):
    template = env.get_template("dashboard.html")
    return template.render(
        categories=categories,
        active_tab="home",
        now_year=datetime.datetime.now().year
    )

def render_member_daily_page(articles, date_str, time_str):
    template = env.get_template("daily_member_news.html")
    return template.render(
        articles=articles,
        date_str=date_str,
        time_str=time_str,
        category_display_name="Members",
        active_tab="members",
        now_year=datetime.datetime.now().year,
        root_path="../.." 
    )
