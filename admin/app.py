import streamlit as st
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

st.set_page_config(
    page_title="VAAX Admin",
    page_icon="⚙️",
    layout="wide"
)

st.title("VAAX Admin Dashboard")

# ... (previous imports)
import pandas as pd
import plotly.express as px
from src.utils.env_manager import read_env_file, update_env_file
from src.utils.usage_logger import get_recent_usage, get_daily_stats

# ... (page config remains)

st.title("VAAX Admin Dashboard")

# Tabs
tab1, tab2, tab3 = st.tabs(["Dashboard", "Configuration", "System Logs"])

with tab1:
    st.header("Overview")
    # Quick Stats
    stats = get_daily_stats(days=7)
    if stats:
        df = pd.DataFrame(stats)
        df['date'] = pd.to_datetime(df['date'])
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Calls (7d)", df['calls'].sum())
        with col2:
            st.metric("Est. Cost (7d)", f"${df['cost_sum'].sum():.4f}")
            
        st.subheader("Daily API Cost")
        st.bar_chart(df.set_index('date')['cost_sum'])
        
        st.subheader("Daily Token Usage")
        st.line_chart(df.set_index('date')[['input_sum', 'output_sum']])
    else:
        st.info("No API usage data available yet.")

with tab2:
    st.header("Environment Configuration")
    st.write("Manage secure keys and configuration here. Changes are saved to `.env`.")
    
    current_vars = read_env_file()
    
    # Grouping common keys
    api_keys = ["GEMINI_API_KEY", "GROK_API_KEY", "OPENAI_API_KEY"]
    analytics_keys = ["GOOGLE_ANALYTICS_ID"]
    
    st.subheader("API Keys")
    for key in api_keys:
        val = current_vars.get(key, "")
        new_val = st.text_input(key, value=val, type="password")
        if new_val != val:
            if st.button(f"Update {key}"):
                update_env_file(key, new_val)
                st.success(f"Updated {key}")
                st.rerun()

    st.subheader("Analytics")
    for key in analytics_keys:
        val = current_vars.get(key, "")
        new_val = st.text_input(key, value=val, placeholder="e.g. G-XXXXXXXXXX")
        if new_val != val:
            if st.button(f"Update {key}"):
                update_env_file(key, new_val)
                st.success(f"Updated {key}")
                st.rerun()

    st.subheader("Other Variables")
    # Show other variables not in the groups above
    for key, val in current_vars.items():
        if key not in api_keys and key not in analytics_keys:
             new_val = st.text_input(key, value=val)
             if new_val != val:
                if st.button(f"Update {key}", key=f"btn_{key}"):
                    update_env_file(key, new_val)
                    st.success(f"Updated {key}")
                    st.rerun()

    with st.expander("Add New Variable"):
        new_key = st.text_input("New Key Name")
        new_val_input = st.text_input("New Value")
        if st.button("Add Variable"):
            if new_key and new_val_input:
                update_env_file(new_key, new_val_input)
                st.success(f"Added {new_key}")
                st.rerun()

with tab3:
    st.header("Recent API Calls")
    logs = get_recent_usage(limit=50)
    if logs:
        st.dataframe(logs)
    else:
        st.info("No logs found.")


