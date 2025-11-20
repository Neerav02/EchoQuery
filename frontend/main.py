import streamlit as st
import requests
import time

# --- CONFIGURATION ---
# We use port 80 because inside Docker, the API listens on port 80
API_URL = "http://api:80" 

st.set_page_config(page_title="EchoQuery AI", page_icon="🎙️", layout="wide")

st.title("🎙️ EchoQuery: AI Media Analysis")
st.write("Upload audio to generate Transcription, Summary, and Sentiment Analysis.")

# File Uploader
uploaded_file = st.file_uploader("Choose an audio file", type=["mp3", "wav", "mp4", "m4a"])

if uploaded_file is not None:
    if st.button("Analyze Audio"):
        with st.spinner("Uploading file to secure storage..."):
            files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
            try:
                response = requests.post(f"{API_URL}/upload/", files=files)
                
                if response.status_code == 200:
                    job_id = response.json()["job_id"]
                    st.success(f"File uploaded! Job ID: {job_id}")
                    
                    status_placeholder = st.empty()
                    
                    # Poll for results
                    while True:
                        status_res = requests.get(f"{API_URL}/jobs/{job_id}")
                        if status_res.status_code == 200:
                            job_data = status_res.json()
                            status = job_data["status"]
                            
                            if status == "COMPLETED":
                                status_placeholder.success("Processing Complete!")
                                st.divider()
                                
                                # --- DISPLAY RESULTS ---
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    st.subheader("📝 Transcription")
                                    st.text_area("Full Text", job_data["transcript"], height=300)
                                
                                with col2:
                                    st.subheader("🧠 AI Analysis")
                                    st.info(f"**Sentiment:** {job_data['sentiment']}")
                                    st.warning(f"**Summary:** {job_data['summary']}")
                                
                                break
                            
                            elif status == "FAILED":
                                status_placeholder.error("Job Failed. Check logs.")
                                break
                            else:
                                status_placeholder.info(f"Status: {status} (AI is thinking...)")
                                time.sleep(2)
                        else:
                            st.error("API Error")
                            break
                            
            except Exception as e:
                st.error(f"Connection Error: {e}")