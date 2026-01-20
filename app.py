from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import boto3
from boto3.dynamodb.conditions import Key, Attr
import uuid
from datetime import datetime
from decimal import Decimal
from bcrypt import hashpw, gensalt, checkpw
import os
import re
import json
from dotenv import load_dotenv

# testing

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "my_super_secret_fallback")

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

app.json_encoder = DecimalEncoder

print("\n" + "="*80)
print("🎬 CinemaPulse - Real-Time Movie Feedback & Analytics Platform (AWS)")
print("="*80)
print("✅ Using AWS DynamoDB storage")
print("="*80 + "\n")

# ============================================================================
# AWS DYNAMODB CONFIGURATION
# ============================================================================
dynamodb = boto3.resource(
    'dynamodb',
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

# DynamoDB Tables
users_table = dynamodb.Table('CinemaPulse_Users')
movies_table = dynamodb.Table('CinemaPulse_Movies')
reviews_table = dynamodb.Table('CinemaPulse_Reviews')

# ============================================================================
# HELPER FUNCTIONS - VALIDATION
# ============================================================================
def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_logged_in():
    """Check if user is logged in"""
    return 'user_email' in session

# ============================================================================
# INITIALIZATION FUNCTION
# ============================================================================
def initialize_movies():
    """Initialize movies table with initial data from JSON if empty"""
    try:
        response = movies_table.scan(Limit=1)
        if not response.get('Items'):
            print("📽️  Initializing movies database...")
            
            data_file_path = os.path.join(os.path.dirname(__file__), 'data', 'movies.json')
            
            with open(data_file_path, 'r') as f:
                movies_data = json.load(f)
                
            for movie in movies_data:
                # Ensure float for avg_rating if needed, though json handles it
                if 'avg_rating' in movie:
                    movie['avg_rating'] = Decimal(str(movie['avg_rating']))
                    
                movies_table.put_item(Item=movie)
            print(f"✅ {len(movies_data)} movies added to database!")
    except Exception as e:
        print(f"⚠️  Error initializing movies: {e}")

# Initialize on startup
initialize_movies()

# ============================================================================
# USER MANAGEMENT - DYNAMODB
# ============================================================================
def register_user(email, password, name):
    """Register new user in DynamoDB"""
    try:
        if not is_valid_email(email):
            return False, "Invalid email format"
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        if len(name.strip()) < 2:
            return False, "Name must be at least 2 characters"
        
        email = email.strip().lower()
        name = name.strip()
        
        # Check if user already exists
        response = users_table.get_item(Key={'email': email})
        if 'Item' in response:
            return False, "User already exists"
        
        # Hash the password
        hashed_password = hashpw(password.encode('utf-8'), gensalt()).decode('utf-8')
        
        # Store user in DynamoDB
        users_table.put_item(
            Item={
                'email': email,
                'name': name,
                'password': hashed_password,
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'total_reviews': 0,
                'avg_rating': Decimal('0.0'),
                'last_review_date': '',
                'is_active': True
            }
        )
        
        print(f"✅ New user registered: {email}")
        return True, "Registration successful"
        
    except Exception as e:
        print(f"❌ Error registering user: {e}")
        return False, "Registration failed. Please try again."

def login_user(email, password):
    """Login user from DynamoDB"""
    try:
        email = email.strip().lower()
        
        # Fetch user data from DynamoDB
        response = users_table.get_item(Key={'email': email})
        user = response.get('Item')
        
        if not user or not checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            return False, "Invalid email or password"
        
        if not user.get('is_active', True):
            return False, "Account is deactivated"
        
        print(f"✅ User logged in: {email}")
        return True, user
        
    except Exception as e:
        print(f"❌ Error during login: {e}")
        return False, "Login failed. Please try again."

def get_user(email):
    """Get user info from DynamoDB"""
    try:
        email = email.strip().lower()
        response = users_table.get_item(Key={'email': email})
        return response.get('Item')
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None

# ============================================================================
# MOVIE MANAGEMENT - DYNAMODB
# ============================================================================
def get_all_movies():
    """Get all active movies from DynamoDB"""
    try:
        response = movies_table.scan(
            FilterExpression=Attr('active').eq(True)
        )
        movies = response.get('Items', [])
        
        # Handle pagination if there are more items
        while 'LastEvaluatedKey' in response:
            response = movies_table.scan(
                FilterExpression=Attr('active').eq(True),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            movies.extend(response.get('Items', []))
        
        return movies
    except Exception as e:
        print(f"❌ Error getting movies: {e}")
        return []

def get_movie_by_id(movie_id):
    """Get specific movie from DynamoDB"""
    try:
        response = movies_table.get_item(Key={'movie_id': str(movie_id)})
        return response.get('Item')
    except Exception as e:
        print(f"❌ Error getting movie: {e}")
        return None

def update_movie_stats(movie_id):
    """Update movie statistics in DynamoDB"""
    try:
        # Get all reviews for this movie
        response = reviews_table.scan(
            FilterExpression=Attr('movie_id').eq(movie_id)
        )
        movie_reviews = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = reviews_table.scan(
                FilterExpression=Attr('movie_id').eq(movie_id),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            movie_reviews.extend(response.get('Items', []))
        
        total_reviews = len(movie_reviews)
        
        if total_reviews > 0:
            avg_rating = sum(r['rating'] for r in movie_reviews) / total_reviews
        else:
            avg_rating = 0.0
        
        # Update movie stats
        movies_table.update_item(
            Key={'movie_id': movie_id},
            UpdateExpression="SET total_reviews = :total, avg_rating = :avg, last_updated = :updated",
            ExpressionAttributeValues={
                ':total': total_reviews,
                ':avg': Decimal(str(round(avg_rating, 2))),
                ':updated': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
        return True
    except Exception as e:
        print(f"❌ Error updating movie stats: {e}")
        return False

# ============================================================================
# REVIEW MANAGEMENT - DYNAMODB
# ============================================================================
def submit_review(name, email, movie_id, rating, feedback_text):
    """Submit a movie review to DynamoDB"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        review_id = str(uuid.uuid4())
        
        reviews_table.put_item(
            Item={
                'review_id': review_id,
                'user_email': email,
                'movie_id': movie_id,
                'name': name,
                'rating': int(rating),
                'feedback': feedback_text,
                'created_at': timestamp,
                'display_date': timestamp
            }
        )
        
        # Update movie and user statistics
        update_movie_stats(movie_id)
        update_user_stats(email)
        
        print(f"✅ Review submitted: {review_id}")
        return True
    except Exception as e:
        print(f"❌ Error submitting review: {e}")
        return False

def get_movie_reviews(movie_id, limit=50):
    """Get all reviews for a movie from DynamoDB"""
    try:
        response = reviews_table.scan(
            FilterExpression=Attr('movie_id').eq(movie_id)
        )
        movie_reviews = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = reviews_table.scan(
                FilterExpression=Attr('movie_id').eq(movie_id),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            movie_reviews.extend(response.get('Items', []))
        
        # Sort by creation date (newest first)
        movie_reviews.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return movie_reviews[:limit]
    except Exception as e:
        print(f"❌ Error getting movie reviews: {e}")
        return []

def get_user_reviews(email):
    """Get all reviews by user from DynamoDB"""
    try:
        response = reviews_table.scan(
            FilterExpression=Attr('user_email').eq(email)
        )
        user_reviews = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = reviews_table.scan(
                FilterExpression=Attr('user_email').eq(email),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            user_reviews.extend(response.get('Items', []))
        
        # Sort by creation date (newest first)
        user_reviews.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Enrich reviews with movie details
        all_movies = get_all_movies()
        movie_dict = {m['movie_id']: m for m in all_movies}
        
        for review in user_reviews:
            movie = movie_dict.get(review['movie_id'])
            if movie:
                review['movie_title'] = movie['title']
                review['movie_genre'] = movie['genre']
                review['movie_image'] = movie['image_url']
                review['release_year'] = movie.get('release_year', 2025)
        
        return user_reviews
    except Exception as e:
        print(f"❌ Error getting user reviews: {e}")
        return []

def update_user_stats(email):
    """Update user statistics in DynamoDB"""
    try:
        # Get all reviews by this user
        response = reviews_table.scan(
            FilterExpression=Attr('user_email').eq(email)
        )
        user_reviews = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = reviews_table.scan(
                FilterExpression=Attr('user_email').eq(email),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            user_reviews.extend(response.get('Items', []))
        
        total_reviews = len(user_reviews)
        
        if total_reviews > 0:
            avg_rating = sum(r['rating'] for r in user_reviews) / total_reviews
            last_review = max(r['created_at'] for r in user_reviews)
        else:
            avg_rating = 0.0
            last_review = ''
        
        # Update user stats
        users_table.update_item(
            Key={'email': email},
            UpdateExpression="SET total_reviews = :total, avg_rating = :avg, last_review_date = :last",
            ExpressionAttributeValues={
                ':total': total_reviews,
                ':avg': Decimal(str(round(avg_rating, 2))),
                ':last': last_review
            }
        )
        return True
    except Exception as e:
        print(f"❌ Error updating user stats: {e}")
        return False

# ============================================================================
# RECOMMENDATIONS ENGINE
# ============================================================================
def get_recommendations(email, limit=5):
    """Get personalized movie recommendations"""
    try:
        all_movies = get_all_movies()
        user_reviews = get_user_reviews(email)
        
        # If no reviews, return top-rated movies
        if not user_reviews:
            return sorted(all_movies, key=lambda x: x.get('avg_rating', 0), reverse=True)[:limit]
        
        # Analyze user preferences
        rated_movie_ids = set()
        genre_ratings = {}
        
        for review in user_reviews:
            rated_movie_ids.add(review['movie_id'])
            rating = review.get('rating', 0)
            genre = review.get('movie_genre', 'Unknown')
            
            if genre not in genre_ratings:
                genre_ratings[genre] = []
            genre_ratings[genre].append(rating)
        
        # Find favorite genres (avg rating >= 4)
        favorite_genres = []
        for genre, ratings in genre_ratings.items():
            avg = sum(ratings) / len(ratings)
            if avg >= 4:
                favorite_genres.append(genre)
        
        # Get unwatched movies from favorite genres
        recommendations = [
            m for m in all_movies 
            if m['movie_id'] not in rated_movie_ids 
            and m.get('genre') in favorite_genres
        ]
        
        # Sort by rating
        recommendations.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
        
        # Fill with other top-rated movies if needed
        if len(recommendations) < limit:
            other_movies = [
                m for m in all_movies 
                if m['movie_id'] not in rated_movie_ids 
                and m not in recommendations
            ]
            other_movies.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
            recommendations.extend(other_movies[:limit - len(recommendations)])
        
        return recommendations[:limit]
    except Exception as e:
        print(f"❌ Error getting recommendations: {e}")
        return []

# ============================================================================
# ANALYTICS FUNCTIONS
# ============================================================================
def get_total_reviews_count():
    """Get total number of reviews from DynamoDB"""
    try:
        response = reviews_table.scan(Select='COUNT')
        count = response.get('Count', 0)
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = reviews_table.scan(
                Select='COUNT',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            count += response.get('Count', 0)
        
        return count
    except Exception as e:
        print(f"❌ Error getting total reviews: {e}")
        return 0

def get_genre_distribution():
    """Get distribution of movies by genre"""
    try:
        movies = get_all_movies()
        genres = {}
        for movie in movies:
            genre = movie.get('genre', 'Unknown')
            genres[genre] = genres.get(genre, 0) + 1
        return genres
    except Exception as e:
        print(f"❌ Error getting genre distribution: {e}")
        return {}

def get_most_reviewed_movies(limit=5):
    """Get most reviewed movies"""
    try:
        movies = get_all_movies()
        return sorted(movies, key=lambda x: x.get('total_reviews', 0), reverse=True)[:limit]
    except Exception as e:
        print(f"❌ Error getting most reviewed: {e}")
        return []

# ============================================================================
# FLASK ROUTES - AUTHENTICATION
# ============================================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Handle JSON request (AJAX) or Form request
        if request.is_json:
            data = request.get_json()
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')
            name = data.get('name', '').strip()
        else:
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            name = request.form.get('name', '').strip()
        
        success, message = register_user(email, password, name)
        
        # Return JSON for AJAX requests
        if request.is_json:
            if success:
                flash('Registration successful! Please login.', 'success')
                return jsonify({'success': True, 'redirect': url_for('login')})
            else:
                return jsonify({'success': False, 'error': message})
        
        # Standard Form Handling
        if success:
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'danger')
    
    return render_template('register.html', is_logged_in=is_logged_in())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Handle JSON request (AJAX) or Form request
        if request.is_json:
            data = request.get_json()
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')
        else:
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
        
        success, result = login_user(email, password)
        
        if success:
            user = result
            session['user_email'] = email
            session['user_name'] = user.get('name', email.split('@')[0])
            
            # Return JSON for AJAX requests
            if request.is_json:
                flash('Login successful! Welcome back!', 'success')
                return jsonify({'success': True, 'redirect': url_for('movies')})
            
            flash('Login successful! Welcome back!', 'success')
            return redirect(url_for('movies'))
        else:
            # Return JSON for AJAX requests
            if request.is_json:
                return jsonify({'success': False, 'error': result})
                
            flash(result, 'danger')
    
    return render_template('login.html', is_logged_in=is_logged_in())

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('index'))

# ============================================================================
# FLASK ROUTES - MAIN APPLICATION
# ============================================================================
@app.route('/')
def index():
    return render_template('home.html', is_logged_in=is_logged_in())

@app.route('/movies')
def movies():
    all_movies = get_all_movies()
    genre_filter = request.args.get('genre', 'all').lower()
    
    if genre_filter != 'all':
        all_movies = [m for m in all_movies if m.get('genre', '').lower() == genre_filter]
    
    all_movies.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
    
    # Convert Decimals for template safety
    for m in all_movies:
        if 'avg_rating' in m and isinstance(m['avg_rating'], Decimal):
            m['avg_rating'] = float(m['avg_rating'])
    
    return render_template('movies.html', movies=all_movies, current_genre=genre_filter, is_logged_in=is_logged_in())

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    movie = get_movie_by_id(movie_id)
    
    if not movie:
        flash("Movie not found!", "danger")
        return redirect(url_for('movies'))
    
    feedback_list = get_movie_reviews(movie_id)
    
    # Convert Decimals in feedback list
    for f in feedback_list:
        if 'rating' in f and isinstance(f['rating'], Decimal):
            f['rating'] = int(f['rating'])
            
    # Convert movie avg_rating
    if movie and 'avg_rating' in movie and isinstance(movie['avg_rating'], Decimal):
        movie['avg_rating'] = float(movie['avg_rating'])
    
    return render_template('movie_detail.html', movie=movie, feedback_list=feedback_list, is_logged_in=is_logged_in())

@app.route('/feedback/<movie_id>')
def feedback_page(movie_id):
    if not is_logged_in():
        flash('Please login to submit feedback!', 'info')
        return redirect(url_for('login'))
    
    movie = get_movie_by_id(movie_id)
    
    if not movie:
        flash("Movie not found!", "danger")
        return redirect(url_for('movies'))
    
    return render_template('feedback.html', movie=movie, is_logged_in=is_logged_in())

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback_route():
    try:
        if not is_logged_in():
            flash('Please login to submit feedback!', 'danger')
            return redirect(url_for('login'))
        
        movie_id = request.form.get('movie_id', '').strip()
        feedback_text = request.form.get('feedback', '').strip()
        rating_raw = request.form.get('rating', '')
        
        name = session.get('user_name', '')
        email = session.get('user_email', '')
        
        if not movie_id or not feedback_text or not rating_raw:
            flash('All fields are required!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        try:
            rating = int(rating_raw)
            if rating < 1 or rating > 5:
                raise ValueError("Rating must be between 1 and 5")
        except ValueError:
            flash('Invalid rating value!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        if len(feedback_text) < 10:
            flash('Feedback must be at least 10 characters long!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        movie = get_movie_by_id(movie_id)
        if not movie:
            flash('Invalid movie!', 'danger')
            return redirect(url_for('movies'))
        
        success = submit_review(name, email, movie_id, rating, feedback_text)
        
        if success:
            flash('Thank you for your feedback! 🎉', 'success')
            return redirect(url_for('movie_detail', movie_id=movie_id))
        else:
            flash('Failed to submit feedback. Please try again.', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
    except Exception as e:
        print(f"❌ Error in submit_feedback_route: {e}")
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('movies'))

# ============================================================================
# MY REVIEWS ROUTE
# ============================================================================
@app.route('/my-reviews')
def my_reviews():
    if not is_logged_in():
        flash("Please login to view your reviews", "danger")
        return redirect(url_for('login'))
        
    email = session.get('user_email')
    user_feedback = get_user_feedback(email)
    
    # Convert Decimals to native types for template compatibility
    for review in user_feedback:
        if 'rating' in review and isinstance(review['rating'], Decimal):
            review['rating'] = int(review['rating'])
            
    # Calculate stats
    total_reviews = len(user_feedback)
    avg_user_rating = 0
    if total_reviews > 0:
        total_rating = sum(r['rating'] for r in user_feedback)
        avg_user_rating = total_rating / total_reviews
        
    recommendations = get_recommendations_for_user(email)
    # Convert recommendation decimals too
    for rec in recommendations:
        if 'avg_rating' in rec and isinstance(rec['avg_rating'], Decimal):
            rec['avg_rating'] = float(rec['avg_rating'])
            
    return render_template('my_reviews.html', 
                          user_feedback=user_feedback,
                          total_reviews=total_reviews,
                          avg_user_rating=avg_user_rating,
                          recommendations=recommendations,
                          user_name=session.get('user_name'),
                          user_email=email,
                          is_logged_in=True)

# ============================================================================
# ANALYTICS ROUTE
# ============================================================================
@app.route('/analytics')
def analytics():
    if not is_logged_in():
        flash('Please login to view analytics!', 'info')
        return redirect(url_for('login'))
    
    email = session.get('user_email')
    user = get_user(email)
    user_reviews = get_user_reviews(email)
    recommendations = get_recommendations(email, limit=4)
    
    # User stats
    user_total_reviews = len(user_reviews)
    user_avg_rating = user.get('avg_rating', 0.0) if user else 0.0
    
    # Platform stats
    all_movies = get_all_movies()
    total_movies = len(all_movies)
    total_reviews = get_total_reviews_count()
    genres = get_genre_distribution()
    top_movies = sorted(all_movies, key=lambda x: x.get('avg_rating', 0) * x.get('total_reviews', 0) or 0, reverse=True)[:6]
    most_reviewed = get_most_reviewed_movies(5)
    
    return render_template('analytics.html',
                         user_email=email,
                         user_total_reviews=user_total_reviews,
                         user_avg_rating=user_avg_rating,
                         total_movies=total_movies,
                         total_reviews=total_reviews,
                         genres=genres,
                         top_movies=top_movies,
                         most_reviewed=most_reviewed,
                         recommendations=recommendations,
                         is_logged_in=is_logged_in())

# ============================================================================
# API ENDPOINTS
# ============================================================================
@app.route('/api/movies')
def api_movies():
    movies = get_all_movies()
    return jsonify({'success': True, 'movies': movies})

@app.route('/api/movie/<movie_id>')
def api_movie_detail(movie_id):
    movie = get_movie_by_id(movie_id)
    if movie:
        return jsonify({'success': True, 'movie': movie})
    else:
        return jsonify({'success': False, 'error': 'Movie not found'}), 404

@app.route('/api/movie/<movie_id>/reviews')
def api_movie_reviews(movie_id):
    reviews = get_movie_reviews(movie_id)
    return jsonify({'success': True, 'reviews': reviews})

@app.route('/api/user/reviews')
def api_user_reviews():
    if not is_logged_in():
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    email = session.get('user_email')
    reviews = get_user_reviews(email)
    return jsonify({'success': True, 'reviews': reviews})

@app.route('/api/recommendations')
def api_recommendations():
    if not is_logged_in():
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    email = session.get('user_email')
    recommendations = get_recommendations(email)
    return jsonify({'success': True, 'recommendations': recommendations})

# ============================================================================
# ERROR HANDLERS & CONTEXT PROCESSORS
# ============================================================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', is_logged_in=is_logged_in()), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html', is_logged_in=is_logged_in()), 500

@app.context_processor
def inject_user():
    return {
        'logged_in': is_logged_in(),
        'user_email': session.get('user_email', ''),
        'user_name': session.get('user_name', ''),
    }

@app.context_processor
def inject_genres():
    try:
        movies = get_all_movies()
        genres = sorted(set(m.get('genre', '') for m in movies if m.get('genre')))
        return {'available_genres': genres}
    except:
        return {'available_genres': []}

# ============================================================================
# UTILITY ROUTES
# ============================================================================
@app.route('/search')
def search():
    query = request.args.get('q', '').strip().lower()
    
    if not query:
        flash('Please enter a search term', 'info')
        return redirect(url_for('movies'))
    
    all_movies = get_all_movies()
    results = [
        m for m in all_movies 
        if query in m.get('title', '').lower() 
        or query in m.get('description', '').lower()
        or query in m.get('director', '').lower()
    ]
    
    return render_template('search_results.html', query=query, movies=results, is_logged_in=is_logged_in())

@app.route('/about')
def about():
    return render_template('about.html', is_logged_in=is_logged_in())

@app.route('/contact')
def contact():
    return render_template('contact.html', is_logged_in=is_logged_in())

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'storage': 'aws_dynamodb',
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

# ============================================================================
# RUN APPLICATION
# ============================================================================
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
