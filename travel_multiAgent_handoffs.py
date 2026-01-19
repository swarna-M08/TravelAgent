import os
import json
import asyncio
import requests
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled,Runner

# Load environment variables
load_dotenv()

BASE_URL = os.getenv("BASE_URL") 
API_KEY = os.getenv("API_KEY") 
MODEL_NAME = os.getenv("MODEL_NAME") 
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
AMADEUS_API_KEY = os.getenv("AMADEUS_API_KEY")
AMADEUS_API_SECRET = os.getenv("AMADEUS_API_SECRET")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

if not BASE_URL or not API_KEY or not MODEL_NAME:
    raise ValueError(
        "Please set BASE_URL, API_KEY, and MODEL_NAME."
    )
    

client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
set_tracing_disabled(disabled=True)
    
# --- Models for structured outputs ---
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
    
# --- Tools ---

@function_tool

def get_weather_forecast(lat: float, lon: float) -> str:
    """Get the weather forecast for a city on a specific date."""

    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return "Weather API key not configured."

    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    )

    response = requests.get(url)

    if response.status_code != 200:
        return f"Failed to fetch weather. Error: {response.json().get('message')}"

    data = response.json()
    weather = data["weather"][0]["description"]
    temp = data["main"]["temp"]

    return f"Current weather at ({lat}, {lon}): {weather}, temperature around {temp}°C."

@function_tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search for flights between two cities on a specific date."""

    # This example shows real-style integration

    flights = [
        {
            "airline": "Qatar Airways",
            "departure_time": "09:10",
            "arrival_time": "13:40",
            "price": 420.50,
            "direct": True
        },
        {
            "airline": "Emirates",
            "departure_time": "22:00",
            "arrival_time": "06:30",
            "price": 380.00,
            "direct": False
        }
    ]

    return json.dumps(flights)

@function_tool
def search_hotels(city: str, check_in: str, check_out: str, max_price: float = None) -> str:
    """Search for hotels in a city for specific dates within a price range."""
    headers = {
        "X-RapidAPI-Key": os.getenv("RAPIDAPI_KEY"),
        "X-RapidAPI-Host": "booking-com.p.rapidapi.com"
    }

    # Simplified response format
    hotels = [
        {
            "name": "Hotel Eiffel Paris",
            "location": "Central Paris",
            "price_per_night": 220.00,
            "amenities": ["WiFi", "Pool", "Breakfast"]
        },
        {
            "name": "Seine River View",
            "location": "Riverside",
            "price_per_night": 180.00,
            "amenities": ["WiFi", "Parking"]
        }
    ]

    if max_price:
        hotels = [h for h in hotels if h["price_per_night"] <= max_price]

    return json.dumps(hotels)

# --- Main Travel Agent ---

flight_agent = Agent(
    name="Flight Specialist",
    handoff_description="Specialist agent for finding and recommending flights",
    instructions="""
    You are a flight specialist who helps users find the best flights for their trips.
    
    Use the search_flights tool to find flight options, and then provide personalized recommendations
    based on the user's preferences (price, time, direct vs. connecting).
    
    Always explain the reasoning behind your recommendations.
    
    Format your response in a clear, organized way with flight details and prices.
    """,
    model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
    tools=[search_flights],
    output_type=FlightRecommendation
)

hotel_agent = Agent(
    name="Hotel Specialist",
    handoff_description="Specialist agent for finding and recommending hotels and accommodations",
    instructions="""
    You are a hotel specialist who helps users find the best accommodations for their trips.
    
    Use the search_hotels tool to find hotel options, and then provide personalized recommendations
    based on the user's preferences (location, price, amenities).
    
    Always explain the reasoning behind your recommendations.
    
    Format your response in a clear, organized way with hotel details, amenities, and prices.
    """,
    model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
    tools=[search_hotels],
    output_type=HotelRecommendation
)

travel_agent = Agent(
    name="Travel Planner",
    instructions="""
    You are a comprehensive travel planning assistant that helps users plan their perfect trip.
    
    You can:
    1. Provide weather information for destinations
    2. Create personalized travel itineraries
    3. Hand off to specialists for flights and hotels when needed
    
    Always be helpful, informative, and enthusiastic about travel. Provide specific recommendations
    based on the user's interests and preferences.
    
    When creating travel plans, consider:
    - The weather at the destination
    - Local attractions and activities
    - Budget constraints
    - Travel duration
    
    If the user asks specifically about flights or hotels, hand off to the appropriate specialist agent.
    """,
    model=OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client),
    tools=[get_weather_forecast],
    handoffs=[flight_agent, hotel_agent],
    output_type=TravelPlan
)

# user -> question ->travel (flight , hotel)

# --- Main Function ---

async def main():
    # Example queries to test different aspects of the system
    queries = [
        # "I need a flight from New York to Chicago tomorrow",
        # "Find me a hotel in Paris with a pool for under $300 per night"
        "I want to visit Tokyo for a week with a budget of $3000. What activities do you recommend?"
    ]
    
    for query in queries:
        print("\n" + "="*50)
        print(f"QUERY: {query}")
        
        result = await Runner.run(travel_agent, query)
        
        print("\nFINAL RESPONSE:")
        
        # Format the output based on the type of response
        if hasattr(result.final_output, "airline"):  # Flight recommendation
            flight = result.final_output
            print("\n✈️ FLIGHT RECOMMENDATION ✈️")
            print(f"Airline: {flight.airline}")
            print(f"Departure: {flight.departure_time}")
            print(f"Arrival: {flight.arrival_time}")
            print(f"Price: ${flight.price}")
            print(f"Direct Flight: {'Yes' if flight.direct_flight else 'No'}")
            print(f"\nWhy this flight: {flight.recommendation_reason}")
            
        elif hasattr(result.final_output, "name") and hasattr(result.final_output, "amenities"):  # Hotel recommendation
            hotel = result.final_output
            print("\n🏨 HOTEL RECOMMENDATION 🏨")
            print(f"Name: {hotel.name}")
            print(f"Location: {hotel.location}")
            print(f"Price per night: ${hotel.price_per_night}")
            
            print("\nAmenities:")
            for i, amenity in enumerate(hotel.amenities, 1):
                print(f"  {i}. {amenity}")
                
            print(f"\nWhy this hotel: {hotel.recommendation_reason}")
            
        elif hasattr(result.final_output, "destination"):  # Travel plan
            travel_plan = result.final_output
            print(f"\n🌍 TRAVEL PLAN FOR {travel_plan.destination.upper()} 🌍")
            print(f"Duration: {travel_plan.duration_days} days")
            print(f"Budget: ${travel_plan.budget}")
            
            print("\n🎯 RECOMMENDED ACTIVITIES:")
            for i, activity in enumerate(travel_plan.activities, 1):
                print(f"  {i}. {activity}")
            
            print(f"\n📝 NOTES: {travel_plan.notes}")
        
        else:  # Generic response
            print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())