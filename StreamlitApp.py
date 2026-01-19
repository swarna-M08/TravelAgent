import streamlit as st
import requests
import os
import json
from dotenv import load_dotenv

st.set_page_config(
    page_title="AI Travel Assistant",
    page_icon="✈️",
    layout="wide"
)

load_dotenv()

# API URL Setup
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

# Fixed for Dark Mode)
st.markdown("""
    <style>
    /* Removing forced white background for Dark Mode compatibility */
    .stChatMessage {
        padding: 10px;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🌍 AI Travel Planner")
# to hide port
# st.caption(f"Backend Connected: `{API_URL}`") 

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if isinstance(msg["content"], dict):
             st.json(msg["content"])
        else:
            st.markdown(msg["content"])

# Input Handler
if prompt := st.chat_input("Plan your trip (e.g., 'Find hotels in Paris under $200')"):
    
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # API Call
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    f"{API_URL}/query",
                    json={"query": prompt},
                    timeout=60
                )
                
                if response.status_code == 200:
                    api_response = response.json()
                    data = api_response.get("data")
                    res_type = api_response.get("response_type")
                    
                    display_text = ""

                    # --- Response Formatting ---
                    if res_type == "flight":
                        st.success("✈️ Flight Recommendation")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Airline", data['airline'])
                            st.metric("Price", f"${data['price']}")
                        with col2:
                            st.write(f"**Route:** {data['departure_time']} -> {data['arrival_time']}")
                        st.info(f"**Reason:** {data['recommendation_reason']}")
                        display_text = f"Flight: {data['airline']} (${data['price']})"

                    elif res_type == "hotel":
                        st.success("🏨 Hotel Recommendation")
                        st.subheader(data['name'])
                        st.write(f"📍 **Location:** {data['location']}")
                        st.write(f"💰 **Price:** ${data['price_per_night']}/night")
                        st.write(f"**Amenities:** {', '.join(data['amenities'])}")
                        display_text = f"Hotel: {data['name']}"

                    elif res_type == "travel_plan":
                        st.success(f"🗺️ Plan for {data['destination']}")
                        st.write(f"**Duration:** {data['duration_days']} days | **Budget:** ${data['budget']}")
                        with st.expander("See Activities"):
                            for act in data['activities']:
                                st.write(f"- {act}")
                        display_text = f"Plan for {data['destination']}"

                    else:
                        st.write(str(data))
                        display_text = str(data)

                    st.session_state.messages.append({"role": "assistant", "content": display_text})

                else:
                    st.error(f"Error: {response.status_code}")

            except Exception as e:
                st.error(f"Connection Failed: {e}")