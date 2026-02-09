import streamlit as st
import requests
import json
import pandas as pd

# Constants
API_BASE_URL = "http://localhost:8000"

# Page Config
st.set_page_config(page_title="RAG Job Search", layout="wide")

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "role" not in st.session_state:
    st.session_state.role = "User"
if "scraped_data" not in st.session_state:
    st.session_state.scraped_data = None

# Sidebar - Role Selection
st.sidebar.title("Navigation")
role = st.sidebar.radio("Select Role", ["User", "Admin"])
st.session_state.role = role

def user_chat_interface():
    st.header("Job Search Assistant")
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "sources" in message:
                with st.expander("View Sources"):
                    for src in message["sources"]:
                        st.markdown(f"**[{src.get('title', 'No Title')}]({src.get('url', '#')})** - {src.get('company', '')}")
                        st.text(src.get('description', '')[:200] + "...")

    # Chat Input
    if prompt := st.chat_input("Cari lowongan kerja (misal: 'Backend Engineer di Jakarta')..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # RAG Process
        with st.chat_message("assistant"):
            with st.spinner("Mencari lowongan relevan..."):
                try:
                    # 1. Retrieve
                    retrieve_res = requests.post(
                        f"{API_BASE_URL}/retrieve",
                        json={"query": prompt}
                    )
                    retrieve_data = retrieve_res.json()
                    
                    if retrieve_res.status_code != 200:
                        st.error(f"Error retrieving: {retrieve_data.get('detail')}")
                        return

                    retrieved_jobs = retrieve_data.get("results", [])
                    
                    # 2. Generate
                    generate_res = requests.post(
                        f"{API_BASE_URL}/generate",
                        json={"query": prompt, "retrieved_jobs": retrieved_jobs}
                    )
                    generate_data = generate_res.json()
                    
                    if generate_res.status_code != 200:
                        st.error(f"Error generating: {generate_data.get('detail')}")
                        return

                    answer = generate_data.get("answer", "Maaf, tidak ada jawaban.")
                    
                    st.markdown(answer)
                    
                    with st.expander("View Sources"):
                        for src in retrieved_jobs:
                            st.markdown(f"**[{src.get('title', 'No Title')}]({src.get('url', '#')})** - {src.get('company', '')}")
                            st.text(src.get('text', '')[:200] + "...")

                    # Save assistant message
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "sources": retrieved_jobs
                    })

                except Exception as e:
                    st.error(f"Connection Error: {e}")

def admin_interface():
    st.header("Admin Dashboard")
    
    tab1, tab2 = st.tabs(["Scrape Jobs", "Upload Poster"])
    
    with tab1:
        st.subheader("Scrape Job Portals")
        col1, col2 = st.columns(2)
        with col1:
            platform = st.selectbox("Platform", ["Loker.id", "Glints", "JobStreet"])
        with col2:
            max_page = st.number_input("Max Pages", min_value=1, max_value=10, value=1)
        
        query = st.text_input("Search Query (e.g. Python Developer)")
        
        # Glints cookie uploader
        if platform == "Glints":
            st.info("⚠️ Glints membutuhkan cookie untuk bypass Cloudflare. Upload file cookie JSON dari browser.")
            cookie_file = st.file_uploader("Upload Glints Cookies (JSON)", type=["json"], key="glints_cookies")
            
            if cookie_file is not None:
                # Save uploaded cookie file temporarily
                import os
                cookie_path = os.path.join(os.path.dirname(__file__), "scrapping", "glints_cookies.json")
                with open(cookie_path, "wb") as f:
                    f.write(cookie_file.getvalue())
                st.success(f"✅ Cookie file uploaded and saved!")
        
        if st.button("Start Scraping"):
            with st.spinner(f"Scraping {platform}..."):
                if platform == "Loker.id":
                    endpoint = "/scrapping/loker-id"
                elif platform == "Glints":
                    endpoint = "/scrapping/glints"
                else:  # JobStreet
                    endpoint = "/scrapping/jobstreet"
                
                try:
                    res = requests.post(
                        f"{API_BASE_URL}{endpoint}",
                        json={"query": query, "max_page": max_page}
                    )
                    if res.status_code == 200:
                        data = res.json().get("data", [])
                        st.success(f"Ditemukan {len(data)} lowongan!")
                        st.session_state.scraped_data = data
                    else:
                        st.error(f"Error: {res.text}")
                except Exception as e:
                    st.error(f"Connection Error: {e}")

        if st.session_state.scraped_data:
            st.dataframe(pd.DataFrame(st.session_state.scraped_data))
            
            if st.button("💾 Save to Database"):
                with st.spinner("Saving to Postgres & Qdrant..."):
                    try:
                        save_res = requests.post(
                            f"{API_BASE_URL}/store",
                            json={"data": st.session_state.scraped_data}
                        )
                        if save_res.status_code == 200:
                            st.success("Berhasil disimpan!")
                            st.json(save_res.json())
                            st.session_state.scraped_data = None # Clear after save
                        else:
                            st.error(f"Save failed: {save_res.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    with tab2:
        st.subheader("Extract Job from Poster Image")
        uploaded_file = st.file_uploader("Upload Job Poster", type=["jpg", "png", "jpeg"])
        
        if uploaded_file is not None:
            st.image(uploaded_file, caption="Preview", width=300)
            
            if st.button("Process & Upload"):
                with st.spinner("Uploading to Supabase & Analyzing with AI..."):
                    try:
                        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                        res = requests.post(f"{API_BASE_URL}/store/upload-image", files=files)
                        
                        if res.status_code == 200:
                            result = res.json()
                            st.success("Upload & Extraction Success!")
                            st.json(result)
                        else:
                            st.error(f"Error: {res.text}")
                    except Exception as e:
                        st.error(f"Connection Error: {e}")

# Main Routing
if st.session_state.role == "Admin":
    admin_interface()
else:
    user_chat_interface()
