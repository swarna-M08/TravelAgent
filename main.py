import os
import json
import requests
from typing import List, Optional, Union, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled

# --- 1. Load Environment Variables ---
load_dotenv() 

BASE_URL = os.getenv("BASE_URL")
API_KEY = os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

if not BASE_URL or not API_KEY or not MODEL_NAME:
    raise ValueError("Please set BASE_URL, API_KEY, and MODEL_NAME in your .env file.")

# --- 2. Setup Client ---
client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
set_tracing_disabled(disabled=True)

# --- 3. Pydantic Models ---
class FlightRecommendation(BaseModel):
    airline: str
    departure_time: str
    arrival_time: str
    price: float
    direct_flight: bool
    recommendation_reason: str
    
class HotelRecommendation(BaseModel):
    name: str
    location: str
    price_per_night: float
    amenities: List[str]
    recommendation_reason: str    

class TravelPlan(BaseModel):
    destination: str
    duration_days: int
    budget: float
    activities: List[str] = Field(description="List of recommended activities")
    notes: str = Field(description="Additional notes or recommendations")

class TravelQueryRequest(BaseModel):
    query: str = Field(..., description="User's travel question")

class TravelResponse(BaseModel):
    success: bool
    response_type: str  # "flight", "hotel", "travel_plan", "general"
    data: Union[FlightRecommendation, HotelRecommendation, TravelPlan, str, Dict]
    message: Optional[str] = None

# --- 4. Tools (FIXED: Now Dynamic) ---

@function_tool
def get_weather_forecast(lat: float, lon: float) -> str:
    """Get weather forecast."""
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return "Weather API key missing. Assume sunny."
    
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            weather = data["weather"][0]["description"]
            temp = data["main"]["temp"]
            return f"Weather at ({lat}, {lon}): {weather}, {temp}°C."
        return "Weather unavailable."
    except Exception as e:
        return f"Weather error: {str(e)}"

@function_tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search for flights based on destination."""
    
    # Logic to return relevant flights based on input
    dest_lower = destination.lower()
    
    if "sylhet" in dest_lower:
        flights = [
            {"airline": "Biman Bangladesh", "departure_time": "08:00", "arrival_time": "08:45", "price": 45.00, "direct": True},
            {"airline": "US-Bangla", "departure_time": "14:30", "arrival_time": "15:15", "price": 50.00, "direct": True}
        ]
    elif "bangkok" in dest_lower:
        flights = [
            {"airline": "Thai Airways", "departure_time": "11:00", "arrival_time": "14:30", "price": 350.00, "direct": True},
            {"airline": "Biman Bangladesh", "departure_time": "10:00", "arrival_time": "13:30", "price": 280.00, "direct": True}
        ]
    else:
        # Generic fallback
        flights = [
            {"airline": "Global Air", "departure_time": "09:00", "arrival_time": "12:00", "price": 150.00, "direct": False},
            {"airline": "Eco Fly", "departure_time": "18:00", "arrival_time": "21:00", "price": 120.00, "direct": True}
        ]
        
    return json.dumps(flights)

@function_tool
def search_hotels(city: str, check_in: str = None, check_out: str = None, max_price: float = None) -> str:
    """Search for hotels in a specific city."""
    
    # Logic to return relevant hotels based on city
    city_lower = city.lower()
    
    if "paris" in city_lower:
        hotels = [
            {"name": "Hotel Eiffel Paris", "location": "Central Paris", "price_per_night": 220.00, "amenities": ["WiFi", "Pool"]},
            {"name": "Seine River View", "location": "Riverside", "price_per_night": 180.00, "amenities": ["WiFi", "Parking"]}
        ]
    elif "sylhet" in city_lower:
        hotels = [
            {"name": "Grand Sylhet Hotel", "location": "Airport Road", "price_per_night": 90.00, "amenities": ["Pool", "WiFi", "Buffet"]},
            {"name": "Rose View Hotel", "location": "Shahjalal Upashahar", "price_per_night": 70.00, "amenities": ["Gym", "Breakfast"]}
        ]
    elif "dhaka" in city_lower:
        hotels = [
            {"name": "InterContinental Dhaka", "location": "Minto Road", "price_per_night": 150.00, "amenities": ["Luxury Pool", "Spa"]},
            {"name": "Pan Pacific Sonargaon", "location": "Karwan Bazar", "price_per_night": 130.00, "amenities": ["Gym", "Bar"]}
        ]
    else:
        # Generic fallback for unknown cities
        hotels = [
            {"name": f"{city.title()} City Center Hotel", "location": "Downtown", "price_per_night": 100.00, "amenities": ["WiFi", "Restaurant"]},
            {"name": f"The {city.title()} Inn", "location": "Near Airport", "price_per_night": 80.00, "amenities": ["Parking", "Breakfast"]}
        ]

    # Filter by price if max_price is provided
    if max_price:
        hotels = [h for h in hotels if h["price_per_night"] <= max_price]
        
    return json.dumps(hotels)

# --- 5. Agents ---
flight_agent = Agent(
    name="Flight Specialist",
    instructions="Find flights based on the user's destination. Always check the destination carefully.",
    model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
    tools=[search_flights],
    output_type=FlightRecommendation
)

hotel_agent = Agent(
    name="Hotel Specialist",
    instructions="Find hotels in the specific city requested by the user. Do not guess the city.",
    model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
    tools=[search_hotels],
    output_type=HotelRecommendation
)

travel_agent = Agent(
    name="Travel Planner",
    instructions="""
    You are a travel planner. 
    1. If the user asks for a TRIP PLAN (itinerary, activities), generate the plan yourself using your knowledge base. Do not hand off to the hotel or flight agent unless the user specifically asks to BOOK or FIND hotels/flights.
    2. If the user specifically asks for FLIGHTS, hand off to the Flight Specialist.
    3. If the user specifically asks for HOTELS, hand off to the Hotel Specialist.
    4. Provide budget in the requested currency if possible.
    """,
    model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
    tools=[get_weather_forecast],
    handoffs=[flight_agent, hotel_agent],
    output_type=TravelPlan
)

# --- 6. FastAPI App ---
app = FastAPI(title="AI Travel Agent API")

@app.get("/")
def home():
    return {"message": "Travel Agent API is running"}

@app.post("/query", response_model=TravelResponse)
async def query_agent(request: TravelQueryRequest):
    try:
        # Run the agent
        result = await Runner.run(travel_agent, request.query)
        final = result.final_output
        
        # Identify type
        res_type = "general"
        if hasattr(final, "airline"): res_type = "flight"
        elif hasattr(final, "name") and hasattr(final, "amenities"): res_type = "hotel"
        elif hasattr(final, "destination"): res_type = "travel_plan"
        
        return TravelResponse(
            success=True,
            response_type=res_type,
            data=final,
            message="Success"
        )
    except Exception as e:
        # Fallback if Pydantic validation fails or other errors
        return TravelResponse(
            success=False,
            response_type="error",
            data=str(e),
            message="An error occurred"
        )

if __name__ == "__main__":
    import uvicorn
    # Use 0.0.0.0 for Docker compatibility
    uvicorn.run(app, host="0.0.0.0", port=8000)