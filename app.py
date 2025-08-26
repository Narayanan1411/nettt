
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import io
import json
from typing import Dict, Any
#import tracebacks

# Supabase integration
from supabase import create_client, Client

from network_optimizer import NetworkOptimizer

from utils import validate_csv_structure, get_sample_data_info

# --- Supabase Config ---
SUPABASE_URL = st.secrets["SUPABASE_URL"] if "SUPABASE_URL" in st.secrets else "https://your-project.supabase.co"
SUPABASE_KEY = st.secrets["SUPABASE_KEY"] if "SUPABASE_KEY" in st.secrets else "your-anon-key"

def get_supabase_client():
    if "supabase" not in st.session_state:
        st.session_state["supabase"] = create_client(SUPABASE_URL, SUPABASE_KEY)
    return st.session_state["supabase"]

# Configure page
st.set_page_config(
    page_title="Provider Network Optimizer",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)


def main():
    st.title("🏥 Provider Network Optimizer Dashboard")

    # --- Authentication ---
    if "user" not in st.session_state:
        show_auth_page()
        return

    user = st.session_state["user"]
    role = user.get("role", "user")

    st.sidebar.write(f"👤 Logged in as: {user['email']} ({role})")
    if st.sidebar.button("Logout"):
        st.session_state.pop("user")
        st.rerun()

    # Page navigation based on role
    if role == "admin":
        page = st.selectbox(
            "Choose a feature:",
            ["🔧 Network Optimization", "📍 Find Nearest Providers"],
            index=0
        )
        if page == "🔧 Network Optimization":
            network_optimization_page()
        else:
            provider_finder_page()
    else:
        provider_finder_page()


# --- Authentication Page ---
def show_auth_page():
    st.header("🔐 Login to DataDash")
    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        login_email = st.text_input("Email", key="login_email")
        login_password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", key="login_btn", use_container_width=True):
            supabase = get_supabase_client()
            try:
                res = supabase.auth.sign_in_with_password({"email": login_email, "password": login_password})
                user = res.user
                if user:
                    # Fetch user role from profile table
                    profile = (
                        supabase.table("profiles")
                        .select("role")
                        .eq("id", user.id)
                        .single()
                        .execute()
                    )
                    role = profile.data["role"] if profile.data and "role" in profile.data else "user"
                    st.session_state["user"] = {"email": login_email, "id": user.id, "role": role}
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tab2:
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        reg_role = st.selectbox("Role", ["user", "admin"], key="reg_role")
        if st.button("Register", key="register_btn", use_container_width=True):
            supabase = get_supabase_client()
            try:
                res = supabase.auth.sign_up({"email": reg_email, "password": reg_password})
                user = res.user
                if user:
                    # Insert into profiles table
                    supabase.table("profiles").insert({"id": user.id, "email": reg_email, "role": reg_role}).execute()
                    st.success("Registration successful! Please login.")
                else:
                    st.error("Registration failed.")
            except Exception as e:
                st.error(f"Registration failed: {e}")

def network_optimization_page():
    """Main network optimization interface"""
    st.markdown("Upload provider and member CSV files to optimize your healthcare network")
    
    # Initialize session state
    if 'optimization_results' not in st.session_state:
        st.session_state.optimization_results = None
    if 'processed_data' not in st.session_state:
        st.session_state.processed_data = None
    
    # Sidebar for file uploads and configuration
    with st.sidebar:
        st.header("📁 Data Upload")
        
        # Display sample data requirements
        with st.expander("📋 Required CSV Format", expanded=False):
            st.markdown(get_sample_data_info())
        
        # File upload sections
        st.subheader("Provider Data")
        provider_file = st.file_uploader(
            "Upload Provider CSV",
            type=['csv'],
            key="provider_upload",
            help="CSV file containing provider information"
        )
        
        st.subheader("Member Data")
        member_file = st.file_uploader(
            "Upload Member CSV",
            type=['csv'],
            key="member_upload",
            help="CSV file containing member information"
        )
        
        # Configuration options
        st.header("⚙️ Configuration")
        
        max_drive_time = st.slider(
            "Max Drive Time (minutes)",
            min_value=10,
            max_value=60,
            value=30,
            step=5,
            help="Maximum acceptable drive time from member to provider"
        )
        
        min_coverage = st.slider(
            "Minimum Coverage (%)",
            min_value=80.0,
            max_value=100.0,
            value=95.0,
            step=1.0,
            help="Minimum percentage of members that must be covered"
        )
        
        min_rating = st.slider(
            "Minimum Average Rating",
            min_value=1.0,
            max_value=5.0,
            value=3.0,
            step=0.1,
            help="Minimum acceptable average provider rating"
        )
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if provider_file is not None and member_file is not None:
            if st.button("🚀 Run Optimization", type="primary", use_container_width=True):
                run_optimization(provider_file, member_file, max_drive_time, min_coverage, min_rating)
        else:
            st.info("👆 Please upload both provider and member CSV files to begin optimization")
    
    with col2:
        if st.session_state.optimization_results is not None:
            if st.button("📥 Export Results", use_container_width=True):
                export_results()
    
    # Display results if available
    if st.session_state.optimization_results is not None:
        display_results()
    
    # Display file previews
    display_file_previews(provider_file, member_file)

def provider_finder_page():
    """Provider finder interface for user location lookup"""
    st.markdown("Enter your location coordinates to find the nearest healthcare providers")

    # User input section (always shown)
    st.header("📍 Your Location")

    col1, col2 = st.columns(2)

    with col1:
        user_lat = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=40.7128,  # Default to NYC
            format="%.6f",
            help="Enter your latitude coordinate"
        )

    with col2:
        user_lon = st.number_input(
            "Longitude", 
            min_value=-180.0,
            max_value=180.0,
            value=-74.0060,  # Default to NYC
            format="%.6f",
            help="Enter your longitude coordinate"
        )

    # Configuration (always shown)
    st.header("⚙️ Search Options")

    col1, col2, col3 = st.columns(3)

    with col1:
        num_providers = st.slider(
            "Number of Providers",
            min_value=5,
            max_value=50,
            value=10,
            help="How many nearest providers to show"
        )

    with col2:
        max_distance = st.slider(
            "Max Distance (miles)",
            min_value=5,
            max_value=100,
            value=25,
            help="Maximum distance to search for providers"
        )

    with col3:
        min_rating = st.slider(
            "Minimum Rating",
            min_value=1.0,
            max_value=5.0,
            value=2.0,
            step=0.1,
            help="Minimum CMS rating filter"
        )

    # Search button
    if st.button("🔍 Find Nearest Providers", type="primary", use_container_width=True):
        # Fetch provider data only when searching
        supabase = get_supabase_client()
        user = st.session_state.get("user", {})
        providers_df = None
        try:
            role = user.get("role", "user")
            if role == "admin":
                query = supabase.table("optimized_networks").select("optimized_providers").eq("user_id", user.get("id", "")).order("created_at", desc=True).limit(1)
            else:
                admin_profiles = supabase.table("profiles").select("id").eq("role", "admin").execute()
                admin_ids = [row["id"] for row in admin_profiles.data] if admin_profiles.data else []
                if admin_ids:
                    query = supabase.table("optimized_networks").select("optimized_providers").in_("user_id", admin_ids).order("created_at", desc=True).limit(1)
                else:
                    query = None
            if query:
                res = query.execute()
                if res.data and len(res.data) > 0:
                    providers_json = res.data[0]["optimized_providers"]
                    providers_df = pd.DataFrame(json.loads(providers_json))
        except Exception as e:
            st.warning(f"Could not fetch optimized network from backend: {e}")

        # Fallback to session state if not found
        if providers_df is None and st.session_state.get("processed_data") is not None:
            providers_df = st.session_state.processed_data['providers']

        # Support both 'CMS_Rating' and 'CMS Rating' column names
        if providers_df is not None and 'CMS Rating' in providers_df.columns and 'CMS_Rating' not in providers_df.columns:
            providers_df = providers_df.rename(columns={'CMS Rating': 'CMS_Rating'})

        required_cols = ['Latitude', 'Longitude', 'ProviderId', 'Cost', 'CMS_Rating']
        missing_cols = []
        if providers_df is None:
            st.error("⚠️ No provider data available. Please run network optimization as admin to load provider data.")
            return
        else:
            missing_cols = [col for col in required_cols if col not in providers_df.columns]

        if missing_cols:
            st.error(f"❌ Missing required columns in provider data: {', '.join(missing_cols)}")
            return

        with st.spinner("🔍 Searching for nearest providers..."):
            nearest_providers = find_nearest_providers(
                user_lat, user_lon, providers_df, num_providers, max_distance, min_rating
            )
            if nearest_providers.empty:
                st.warning(f"❌ No providers found within {max_distance} miles with rating ≥ {min_rating}")
            else:
                display_nearest_providers(nearest_providers, user_lat, user_lon)

def find_nearest_providers(user_lat, user_lon, providers_df, num_providers, max_distance, min_rating):
    """Find nearest providers using spatial search"""
    from scipy.spatial import cKDTree
    import numpy as np
    
    # Filter providers by rating
    filtered_providers = providers_df[providers_df['CMS_Rating'] >= min_rating].copy()
    
    if filtered_providers.empty:
        return pd.DataFrame()
    
    # Build spatial index
    provider_coords = filtered_providers[['Latitude', 'Longitude']].values
    tree = cKDTree(provider_coords)
    
    # Find nearest providers
    distances, indices = tree.query(
        [user_lat, user_lon], 
        k=min(num_providers, len(filtered_providers)),
        distance_upper_bound=max_distance / 69.0  # Rough conversion to degrees
    )
    
    # Filter out invalid distances (beyond max_distance)
    valid_mask = distances != np.inf
    if not np.any(valid_mask):
        return pd.DataFrame()
    
    valid_distances = distances[valid_mask]
    valid_indices = indices[valid_mask]
    
    # Get the nearest providers
    nearest_providers = filtered_providers.iloc[valid_indices].copy()
    
    # Calculate accurate distances in miles
    nearest_providers['Distance_Miles'] = [
        calculate_distance(user_lat, user_lon, row['Latitude'], row['Longitude'])
        for _, row in nearest_providers.iterrows()
    ]
    
    # Filter by actual distance and sort
    nearest_providers = nearest_providers[nearest_providers['Distance_Miles'] <= max_distance]
    nearest_providers = nearest_providers.sort_values('Distance_Miles')
    
    return nearest_providers

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points using Haversine formula"""
    import math
    
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Earth radius in miles
    r = 3956
    
    return c * r

def display_nearest_providers(providers_df, user_lat, user_lon):
    """Display the nearest providers with details"""
    st.header("🏥 Nearest Providers")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Providers Found", len(providers_df))
    
    with col2:
        avg_distance = providers_df['Distance_Miles'].mean()
        st.metric("Avg Distance", f"{avg_distance:.1f} mi")
    
    with col3:
        avg_rating = providers_df['CMS_Rating'].mean()
        st.metric("Avg Rating", f"{avg_rating:.2f}")
    
    with col4:
        closest_distance = providers_df['Distance_Miles'].min()
        st.metric("Closest Provider", f"{closest_distance:.1f} mi")
    
    # Providers table
    st.subheader("📋 Provider Details")

    # Show map for the nearest provider (provider only, not user)
    if not providers_df.empty:
        best_provider = providers_df.iloc[0]
        st.markdown("**Best Nearest Provider on Map**")
        map_df = pd.DataFrame({
            'lat': [best_provider['Latitude']],
            'lon': [best_provider['Longitude']],
            'label': [f"Provider: {best_provider['ProviderId']}"]
        })
        st.map(map_df.rename(columns={'lat': 'latitude', 'lon': 'longitude'}), zoom=10)

        # Google Maps directions link (unchanged)
        user_str = f"{user_lat},{user_lon}"
        provider_str = f"{best_provider['Latitude']},{best_provider['Longitude']}"
        gmaps_url = f"https://www.google.com/maps/dir/?api=1&origin={user_str}&destination={provider_str}&travelmode=driving"
        st.markdown(f"[🗺️ Open Route in Google Maps]({gmaps_url})", unsafe_allow_html=True)

    # Format the display data
    display_data = providers_df.copy()
    display_data['Distance_Miles'] = display_data['Distance_Miles'].apply(lambda x: f"{x:.1f}")
    display_data['Cost'] = display_data['Cost'].apply(lambda x: f"${x:,.0f}")
    display_data['CMS_Rating'] = display_data['CMS_Rating'].apply(lambda x: f"{x:.1f}")

    # Select columns for display
    display_columns = ['ProviderId', 'Distance_Miles', 'CMS_Rating', 'Cost']
    if 'ProviderType' in display_data.columns:
        display_columns.insert(1, 'ProviderType')

    st.dataframe(
        display_data[display_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            'ProviderId': 'Provider ID',
            'ProviderType': 'Type',
            'Distance_Miles': 'Distance (mi)',
            'CMS_Rating': 'Rating',
            'Cost': 'Annual Cost'
        }
    )
    
    # Distance distribution chart
    if len(providers_df) > 1:
        st.subheader("📊 Distance Distribution")
        fig_dist = px.histogram(
            providers_df,
            x='Distance_Miles',
            nbins=10,
            title="Provider Distance Distribution",
            labels={'Distance_Miles': 'Distance (miles)', 'count': 'Number of Providers'}
        )
        st.plotly_chart(fig_dist, use_container_width=True)
    
    # Rating vs Distance scatter plot
    if len(providers_df) > 1:
        st.subheader("🎯 Rating vs Distance Analysis")
        fig_scatter = px.scatter(
            providers_df,
            x='Distance_Miles',
            y='CMS_Rating',
            color='ProviderType' if 'ProviderType' in providers_df.columns else None,
            size='Cost',
            title="Provider Rating vs Distance",
            labels={
                'Distance_Miles': 'Distance (miles)',
                'CMS_Rating': 'CMS Rating',
                'Cost': 'Annual Cost'
            },
            hover_data={'ProviderId': True, 'Cost': ':,.0f'}
        )
        st.plotly_chart(fig_scatter, use_container_width=True)


def run_optimization(provider_file, member_file, max_drive_time, min_coverage, min_rating):
    """Run the network optimization process and store results in Supabase"""
    with st.spinner("🔄 Processing data and running optimization..."):
        try:
            # Read and validate CSV files
            providers_df = pd.read_csv(provider_file)
            members_df = pd.read_csv(member_file)

            # Validate CSV structure
            provider_validation = validate_csv_structure(providers_df, 'provider')
            member_validation = validate_csv_structure(members_df, 'member')

            if not provider_validation['valid']:
                st.error(f"❌ Provider CSV validation failed: {provider_validation['message']}")
                return

            if not member_validation['valid']:
                st.error(f"❌ Member CSV validation failed: {member_validation['message']}")
                return

            # Initialize optimizer with configuration
            optimizer = NetworkOptimizer(
                max_drive_min=max_drive_time,
                min_coverage_pct=min_coverage,
                min_avg_rating=min_rating
            )

            # Run optimization with progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            progress_container = st.container()

            status_text.text("🔍 Analyzing provider data...")
            progress_bar.progress(20)

            status_text.text("👥 Processing member data...")
            progress_bar.progress(40)

            status_text.text("🧮 Building candidate pairs...")
            progress_bar.progress(60)

            status_text.text("⚡ Running optimization algorithm...")
            progress_bar.progress(80)

            # Add a live log container for real-time updates
            log_container = progress_container.empty()

            class StreamlitProgressHandler:
                def __init__(self, log_container, status_text):
                    self.log_container = log_container
                    self.status_text = status_text
                    self.removed_count = 0
                    self.logs = []

                def update_progress(self, message):
                    if "Removed provider" in message:
                        self.removed_count += 1
                        self.status_text.text(f"🔧 Optimizing network... Removed {self.removed_count} providers")
                        # Keep only last 10 log entries
                        self.logs.append(message)
                        if len(self.logs) > 10:
                            self.logs.pop(0)
                        self.log_container.text("\n".join(self.logs[-5:]))  # Show last 5 entries

            # Create progress handler and pass to optimizer
            progress_handler = StreamlitProgressHandler(log_container, status_text)
            optimizer.progress_handler = progress_handler

            results = optimizer.optimize(members_df, providers_df)

            status_text.text("✅ Optimization complete!")
            progress_bar.progress(100)

            # Store results in session state
            st.session_state.optimization_results = results
            st.session_state.processed_data = {
                'providers': providers_df,
                'members': members_df,
                'config': {
                    'max_drive_time': max_drive_time,
                    'min_coverage': min_coverage,
                    'min_rating': min_rating
                }
            }

            # --- Store optimized provider data in Supabase ---
            user = st.session_state.get("user", {})
            supabase = get_supabase_client()
            try:
                # Save all columns of optimized providers (not just a subset)
                optimized_provider_ids = results['final_assignments']['ProviderId'].unique().tolist()
                all_cols = providers_df.columns.tolist()
                optimized_providers_full = providers_df[providers_df['ProviderId'].isin(optimized_provider_ids)][all_cols].to_dict('records')
                supabase.table("optimized_networks").insert({
                    "user_id": user.get("id", ""),
                    "email": user.get("email", ""),
                    "config": json.dumps({
                        "max_drive_time": max_drive_time,
                        "min_coverage": min_coverage,
                        "min_rating": min_rating
                    }),
                    "optimized_providers": json.dumps(optimized_providers_full)
                }).execute()
            except Exception as db_exc:
                st.warning(f"Could not save to backend: {db_exc}")

            # Clear progress indicators
            progress_bar.empty()
            status_text.empty()

            st.success("🎉 Network optimization completed successfully!")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error during optimization: {str(e)}")
            st.expander("🔍 Error Details", expanded=False).code(traceback.format_exc())

def display_results():
    """Display optimization results with visualizations"""
    results = st.session_state.optimization_results
    data = st.session_state.processed_data
    
    st.header("📊 Optimization Results")
    
    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Coverage",
            f"{results['coverage_pct']:.1f}%",
            help="Percentage of members assigned to providers"
        )
    
    with col2:
        st.metric(
            "Average Rating",
            f"{results['avg_rating']:.2f}",
            help="Average CMS rating of selected providers"
        )
    
    with col3:
        st.metric(
            "Total Cost",
            f"${results['total_cost']:,.0f}",
            help="Total annual cost of selected providers"
        )
    
    with col4:
        st.metric(
            "Providers Used",
            f"{results['providers_used']}",
            help="Number of providers in optimized network"
        )
    
    # Before vs After Comparison
    display_before_after_comparison(results, data)
    
    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📈 Analytics", "📋 Assignments", "📊 Provider Details"])
    
    with tab1:
        display_analytics(results, data)
    
    with tab2:
        display_assignments(results)
    
    with tab3:
        display_provider_details(results, data)

def display_analytics(results, data):
    """Display analytics charts and insights"""
    assignments = results['final_assignments']
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Provider type distribution
        if not assignments.empty:
            type_counts = assignments['ProviderType'].value_counts()
            fig_pie = px.pie(
                values=type_counts.values,
                names=type_counts.index,
                title="Provider Distribution by Type"
            )
            st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # Rating distribution
        if not assignments.empty:
            fig_hist = px.histogram(
                assignments,
                x='CMS_Rating',
                nbins=10,
                title="Provider Rating Distribution",
                labels={'CMS_Rating': 'CMS Rating', 'count': 'Number of Providers'}
            )
            st.plotly_chart(fig_hist, use_container_width=True)
    
    # Cost analysis
    if not assignments.empty:
        provider_costs = assignments.groupby('ProviderId').agg({
            'Cost': 'first',
            'MemberId': 'count',
            'CMS_Rating': 'first'
        }).rename(columns={'MemberId': 'Members_Assigned'})
        
        provider_costs['Cost_Per_Member'] = provider_costs['Cost'] / provider_costs['Members_Assigned']
        
        fig_scatter = px.scatter(
            provider_costs,
            x='Members_Assigned',
            y='Cost_Per_Member',
            color='CMS_Rating',
            size='Cost',
            title="Provider Cost Efficiency Analysis",
            labels={
                'Members_Assigned': 'Members Assigned',
                'Cost_Per_Member': 'Cost per Member ($)',
                'CMS_Rating': 'CMS Rating'
            },
            hover_data={'Cost': ':,.0f'}
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

def display_before_after_comparison(results, data):
    """Display comprehensive before vs after optimization comparison"""
    st.subheader("🔄 Before vs After Optimization")

    # Calculate original network metrics
    providers_df = data['providers']
    members_df = data['members']

    # Support both 'CMS_Rating' and 'CMS Rating' column names
    if 'CMS Rating' in providers_df.columns and 'CMS_Rating' not in providers_df.columns:
        providers_df = providers_df.rename(columns={'CMS Rating': 'CMS_Rating'})
    if 'CMS_Rating' not in providers_df.columns:
        st.error("❌ Provider data missing 'CMS_Rating' column. Please check your CSV file.")
        return

    # Original network metrics (all providers)
    original_cost = providers_df['Cost'].sum()
    original_providers = len(providers_df)
    original_avg_rating = providers_df['CMS_Rating'].mean()

    # Optimized network metrics
    optimized_cost = results['total_cost']
    optimized_providers = results['providers_used']
    optimized_avg_rating = results['avg_rating']
    optimized_coverage = results['coverage_pct']

    # Calculate savings
    cost_savings = original_cost - optimized_cost
    savings_percentage = (cost_savings / original_cost) * 100
    providers_removed = original_providers - optimized_providers
    reduction_percentage = (providers_removed / original_providers) * 100

    # Main comparison metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Network Cost",
            f"${optimized_cost:,.0f}",
            delta=f"-${cost_savings:,.0f} ({savings_percentage:.1f}%)",
            delta_color="inverse"
        )

    with col2:
        st.metric(
            "Providers Used",
            f"{optimized_providers}",
            delta=f"-{providers_removed} ({reduction_percentage:.1f}%)",
            delta_color="inverse"
        )

    with col3:
        rating_change = optimized_avg_rating - original_avg_rating
        st.metric(
            "Average Rating",
            f"{optimized_avg_rating:.2f}",
            delta=f"{rating_change:+.2f}",
            delta_color="normal"
        )

    with col4:
        st.metric(
            "Member Coverage",
            f"{optimized_coverage:.1f}%",
            help="Percentage of members assigned to providers"
        )

    # Detailed comparison charts
    st.subheader("📊 Detailed Comparison")

    col1, col2 = st.columns(2)

    with col1:
        # Cost comparison bar chart
        comparison_data = {
            'Network': ['Original', 'Optimized'],
            'Cost': [original_cost, optimized_cost]
        }
        fig_cost = px.bar(
            comparison_data,
            x='Network',
            y='Cost',
            title="Total Network Cost Comparison",
            color='Network',
            color_discrete_map={'Original': '#ff7f7f', 'Optimized': '#7fbf7f'}
        )
        fig_cost.update_layout(showlegend=False)
        st.plotly_chart(fig_cost, use_container_width=True)

    with col2:
        # Provider count comparison
        comparison_providers = {
            'Network': ['Original', 'Optimized'],
            'Providers': [original_providers, optimized_providers]
        }
        fig_providers = px.bar(
            comparison_providers,
            x='Network',
            y='Providers',
            title="Provider Count Comparison",
            color='Network',
            color_discrete_map={'Original': '#ff7f7f', 'Optimized': '#7fbf7f'}
        )
        fig_providers.update_layout(showlegend=False)
        st.plotly_chart(fig_providers, use_container_width=True)

    # Summary insights
    st.subheader("💡 Key Insights")

    insights = []
    insights.append(f"**Cost Savings**: Achieved ${cost_savings:,.0f} savings ({savings_percentage:.1f}% reduction)")
    insights.append(f"**Network Efficiency**: Reduced provider count by {providers_removed} ({reduction_percentage:.1f}%)")

    if rating_change > 0:
        insights.append(f"**Quality Improvement**: Average provider rating increased by {rating_change:.2f} points")
    elif rating_change < -0.1:
        insights.append(f"**Quality Trade-off**: Average provider rating decreased by {abs(rating_change):.2f} points")
    else:
        insights.append(f"**Quality Maintained**: Average provider rating remained stable")

    insights.append(f"**Coverage**: {optimized_coverage:.1f}% of members successfully assigned to providers")

    for insight in insights:
        st.write(f"• {insight}")

    # Provider type analysis if available
    assignments = results['final_assignments']
    if not assignments.empty and 'ProviderType' in assignments.columns:
        st.subheader("🏥 Provider Type Analysis")

        # Original provider types
        original_types = providers_df['ProviderType'].value_counts() if 'ProviderType' in providers_df.columns else None

        # Optimized provider types
        optimized_types = assignments['ProviderType'].value_counts()

        if original_types is not None:
            # Create comparison dataframe
            comparison_df = pd.DataFrame({
                'Original': original_types,
                'Optimized': optimized_types
            }).fillna(0)

            # Provider type comparison chart
            fig_types = px.bar(
                comparison_df.reset_index(),
                x='ProviderType',
                y=['Original', 'Optimized'],
                title="Provider Count by Type: Before vs After",
                barmode='group'
            )
            st.plotly_chart(fig_types, use_container_width=True)

def display_assignments(results):
    """Display member-provider assignments table"""
    assignments = results['final_assignments']
    
    if assignments.empty:
        st.warning("No assignments to display")
        return
    
    # Summary statistics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        avg_rating = assignments['CMS_Rating'].mean()
        st.metric("Avg Provider Rating", f"{avg_rating:.2f}")
    
    with col2:
        total_members = len(assignments)
        st.metric("Total Assignments", f"{total_members:,}")
    
    with col3:
        unique_providers = assignments['ProviderId'].nunique()
        st.metric("Unique Providers", f"{unique_providers}")
    
    # Assignments table with filtering
    st.subheader("Assignment Details")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        provider_types = ['All'] + sorted(assignments['ProviderType'].unique().tolist())
        selected_type = st.selectbox("Filter by Provider Type", provider_types)
    
    with col2:
        min_rating_filter = st.slider("Minimum Rating", 1.0, 5.0, 1.0, 0.1)
    
    with col3:
        max_cost_filter = st.number_input(
            "Maximum Cost", 
            min_value=0,
            max_value=int(assignments['Cost'].max()),
            value=int(assignments['Cost'].max())
        )
    
    # Apply filters
    filtered_assignments = assignments.copy()
    
    if selected_type != 'All':
        filtered_assignments = filtered_assignments[filtered_assignments['ProviderType'] == selected_type]
    
    filtered_assignments = filtered_assignments[
        (filtered_assignments['CMS_Rating'] >= min_rating_filter) &
        (filtered_assignments['Cost'] <= max_cost_filter)
    ]
    
    # Display filtered table
    st.dataframe(
        filtered_assignments[['MemberId', 'ProviderId', 'ProviderType', 'CMS_Rating', 'Cost']],
        use_container_width=True,
        hide_index=True
    )
    
    # Download filtered data
    if not filtered_assignments.empty:
        csv_data = filtered_assignments.to_csv(index=False)
        st.download_button(
            label="📥 Download Filtered Assignments",
            data=csv_data,
            file_name="filtered_assignments.csv",
            mime="text/csv"
        )

def display_provider_details(results, data):
    """Display detailed provider information"""
    assignments = results['final_assignments']
    
    if assignments.empty:
        st.warning("No provider details to display")
        return
    
    # Provider utilization analysis
    provider_stats = assignments.groupby(['ProviderId', 'ProviderType', 'CMS_Rating', 'Cost']).size().reset_index(name='Members_Assigned')
    
    # Sort by members assigned
    provider_stats = provider_stats.sort_values('Members_Assigned', ascending=False)
    
    st.subheader("Provider Utilization")
    
    # Top providers chart
    top_providers = provider_stats.head(15)
    fig_bar = px.bar(
        top_providers,
        x='ProviderId',
        y='Members_Assigned',
        color='CMS_Rating',
        title="Top 15 Providers by Member Assignment",
        labels={'ProviderId': 'Provider ID', 'Members_Assigned': 'Members Assigned'}
    )
    fig_bar.update_layout(xaxis={'tickangle': 45})
    st.plotly_chart(fig_bar, use_container_width=True)
    
    # Detailed provider table
    st.subheader("Provider Summary")
    provider_stats['Cost_Per_Member'] = provider_stats['Cost'] / provider_stats['Members_Assigned']
    
    # Format columns for display
    display_stats = provider_stats.copy()
    display_stats['Cost'] = display_stats['Cost'].apply(lambda x: f"${x:,.0f}")
    display_stats['Cost_Per_Member'] = display_stats['Cost_Per_Member'].apply(lambda x: f"${x:,.0f}")
    display_stats['CMS_Rating'] = display_stats['CMS_Rating'].apply(lambda x: f"{x:.1f}")
    
    st.dataframe(
        display_stats[['ProviderId', 'ProviderType', 'CMS_Rating', 'Members_Assigned', 'Cost', 'Cost_Per_Member']],
        use_container_width=True,
        hide_index=True,
        column_config={
            'ProviderId': 'Provider ID',
            'ProviderType': 'Type',
            'CMS_Rating': 'Rating',
            'Members_Assigned': 'Members',
            'Cost': 'Annual Cost',
            'Cost_Per_Member': 'Cost/Member'
        }
    )

def display_file_previews(provider_file, member_file):
    """Display previews of uploaded files"""
    if provider_file is not None or member_file is not None:
        st.header("📋 Data Preview")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if provider_file is not None:
                st.subheader("Provider Data Preview")
                try:
                    provider_df = pd.read_csv(provider_file)
                    st.dataframe(provider_df.head(10), use_container_width=True)
                    st.caption(f"Shape: {provider_df.shape[0]} rows × {provider_df.shape[1]} columns")
                except Exception as e:
                    st.error(f"Error reading provider file: {str(e)}")
        
        with col2:
            if member_file is not None:
                st.subheader("Member Data Preview")
                try:
                    member_df = pd.read_csv(member_file)
                    st.dataframe(member_df.head(10), use_container_width=True)
                    st.caption(f"Shape: {member_df.shape[0]} rows × {member_df.shape[1]} columns")
                except Exception as e:
                    st.error(f"Error reading member file: {str(e)}")

def export_results():
    """Export optimization results to downloadable formats"""
    if st.session_state.optimization_results is None:
        st.error("No results to export")
        return
    
    results = st.session_state.optimization_results
    
    # Create export data
    assignments = results['final_assignments']
    
    if assignments.empty:
        st.warning("No assignments to export")
        return
    
    # Export options
    col1, col2 = st.columns(2)

    # --- Metrics summary ---
    summary_lines = [
        f"Coverage (%):,{results['coverage_pct']:.1f}",
        f"Average Rating:,{results['avg_rating']:.2f}",
        f"Total Cost:,$ {results['total_cost']:,.0f}",
        f"Providers Used:,{results['providers_used']}"
    ]
    # If available, add cost savings and other enhancements
    data = st.session_state.get('processed_data')
    if data:
        providers_df = data.get('providers')
        if providers_df is not None and 'Cost' in providers_df.columns:
            original_cost = providers_df['Cost'].sum()
            cost_savings = original_cost - results['total_cost']
            savings_pct = (cost_savings / original_cost) * 100 if original_cost else 0
            summary_lines.append(f"Original Cost:,$ {original_cost:,.0f}")
            summary_lines.append(f"Cost Savings:,$ {cost_savings:,.0f} ({savings_pct:.1f}%)")

    summary_csv = '\n'.join(summary_lines) + '\n\n'

    with col1:
        # CSV export with metrics summary at the top
        csv_data = summary_csv + assignments.to_csv(index=False)
        st.download_button(
            label="📄 Download as CSV",
            data=csv_data,
            file_name="network_optimization_results.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col2:
        # JSON export with summary
        export_data = {
            'optimization_summary': {
                'coverage_pct': results['coverage_pct'],
                'avg_rating': results['avg_rating'],
                'total_cost': results['total_cost'],
                'providers_used': results['providers_used'],
            },
            'assignments': assignments.to_dict('records')
        }
        if data and providers_df is not None and 'Cost' in providers_df.columns:
            export_data['optimization_summary']['original_cost'] = original_cost
            export_data['optimization_summary']['cost_savings'] = cost_savings
            export_data['optimization_summary']['savings_pct'] = savings_pct

        json_data = json.dumps(export_data, indent=2, default=str)
        st.download_button(
            label="📊 Download as JSON",
            data=json_data,
            file_name="network_optimization_results.json",
            mime="application/json",
            use_container_width=True
        )

    st.success("✅ Export options ready!")

if __name__ == "__main__":
    main()

# Note: The deploy button is not present in this code. If you see a deploy button, it may be injected by Streamlit Cloud or your environment. It cannot be removed from the codebase.
