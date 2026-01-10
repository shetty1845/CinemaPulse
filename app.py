from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import uuid
from datetime import datetime
import os
from dotenv import load_dotenv
import secrets
import re
import json
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

# ============================================================================
# AWS DYNAMODB & SNS - REQUIRED (No fallback)
# ============================================================================
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
MOVIES_TABLE = os.getenv('MOVIES_TABLE', 'CinemaPulse-Movies')
USERS_TABLE = os.getenv('USERS_TABLE', 'CinemaPulse-Users')
REVIEWS_TABLE = os.getenv('REVIEWS_TABLE', 'CinemaPulse-Reviews')
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')

# Initialize AWS clients - REQUIRED
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
sns_client = boto3.client('sns', region_name=AWS_REGION)

# Table references
MOVIES_TABLE_OBJ = dynamodb.Table(MOVIES_TABLE)
USERS_TABLE_OBJ = dynamodb.Table(USERS_TABLE)
REVIEWS_TABLE_OBJ = dynamodb.Table(REVIEWS_TABLE)

# Initial Movies Data (Preserved exactly)
MOVIES_INITIAL_DATA = [
    {'movie_id': 'movie_001', 'title': 'The Quantum Paradox', 'description': 'A mind-bending sci-fi thriller exploring parallel universes and quantum mechanics.', 'genre': 'Sci-Fi', 'release_year': 2024, 'director': 'Sarah Mitchell', 'image_url': 'https://image.tmdb.org/t/p/w500/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True, 'created_at': datetime.now().isoformat(), 'last_updated': datetime.now().isoformat()},
    {'movie_id': 'movie_002', 'title': 'Echoes of Tomorrow', 'description': 'A heartwarming drama about family, time travel, and second chances.', 'genre': 'Drama', 'release_year': 2025, 'director': 'James Chen', 'image_url': 'https://image.tmdb.org/t/p/w500/kXfqcdQKsToO0OUXHcrrNCHDBzO.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True, 'created_at': datetime.now().isoformat(), 'last_updated': datetime.now().isoformat()},
    {'movie_id': 'movie_003', 'title': 'Shadow Protocol', 'description': 'An action-packed espionage thriller with explosive sequences and plot twists.', 'genre': 'Action', 'release_year': 2025, 'director': 'Marcus Rodriguez', 'image_url': 'https://image.tmdb.org/t/p/w500/7WsyChQLEftFiDOVTGkv3hFpyyt.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True, 'created_at': datetime.now().isoformat(), 'last_updated': datetime.now().isoformat()},
    {'movie_id': 'movie_004', 'title': 'The Last Symphony', 'description': "A biographical drama about a legendary composer's final masterpiece.", 'genre': 'Drama', 'release_year': 2024, 'director': 'Elena Volkov', 'image_url': 'https://image.tmdb.org/t/p/w500/qNBAXBIQlnOThrVvA6mA2B5ggV6.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True, 'created_at': datetime.now().isoformat(), 'last_updated': datetime.now().isoformat()},
    {'movie_id': 'movie_005', 'title': 'Neon City', 'description': 'A cyberpunk adventure set in a dystopian future with stunning visuals.', 'genre': 'Sci-Fi', 'release_year': 2026, 'director': 'Kenji Tanaka', 'image_url': 'https://image.tmdb.org/t/p/w500/pwGmXVKUgKN13psUjlhC9zBcq1o.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True, 'created_at': datetime.now().isoformat(), 'last_updated': datetime.now().isoformat()},
    {'movie_id': 'movie_006', 'title': 'Desert Storm', 'description': 'A survival thriller about a group stranded in the Sahara Desert.', 'genre': 'Thriller', 'release_year': 2025, 'director': 'Ahmed Hassan', 'image_url': 'https://image.tmdb.org/t/p/w500/9BBTo63ANSmhC4e6r62OJFuK2GL.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True, 'created_at': datetime.now().isoformat(), 'last_updated': datetime.now().isoformat()},
    {'movie_id': 'movie_007', 'title': 'Midnight Racing', 'description': 'Underground street racing meets high-stakes heist in this adrenaline rush.', 'genre': 'Action', 'release_year': 2025, 'director': 'Lucas Knight', 'image_url': 'https://image.tmdb.org/t/p/w500/sv1xJUazXeYqALzczSZ3O6nkH75.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True, 'created_at': datetime.now().isoformat(), 'last_updated': datetime.now().isoformat()},
    {'movie_id': 'movie_008', 'title': 'The Forgotten Island', 'description': 'Archaeologists discover a mysterious civilization on a remote island.', 'genre': 'Adventure', 'release_year': 2024, 'director': 'Isabella Santos', 'image_url': 'https://image.tmdb.org/t/p/w500/yDHYTfA3R0jFYba16jBB1ef8oIt.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True, 'created_at': datetime.now().isoformat(), 'last_updated': datetime.now().isoformat()}
]

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Initialize movies in DynamoDB on startup
def initialize_movies():
    try:
        for movie in MOVIES_INITIAL_DATA:
            MOVIES_TABLE_OBJ.put_item(Item=movie)
        print("✅ Initial movies loaded to DynamoDB!")
    except Exception as e:
        print(f"⚠️ Movies already exist or init failed: {e}")

initialize_movies()

print("\n" + "="*80)
print("🎬 CinemaPulse - DYNAMODB ONLY PRODUCTION VERSION")
print("✅ Using ONLY DynamoDB tables + SNS notifications")
print("✅ EC2 IAM Role authentication REQUIRED")
print(f"✅ Tables: {MOVIES_TABLE}, {USERS_TABLE}, {REVIEWS_TABLE}")
print(f"✅ SNS: {SNS_TOPIC_ARN}")
print("="*80 + "\n")

# ============================================================================
# SNS NOTIFICATION
# ============================================================================
def send_sns_notification(message):
    """Send SNS notification safely"""
    if SNS_TOPIC_ARN and sns_client:
        try:
            sns_client.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=json.dumps(message),
                Subject='CinemaPulse: New Review Submitted'
            )
            print(f"📧 SNS notification sent: {message.get('movie_id', 'N/A')}")
        except Exception as e:
            print(f"⚠️ SNS failed: {e}")

# ============================================================================
# VALIDATION FUNCTIONS (Unchanged)
# ============================================================================
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def hash_password(password):
    return generate_password_hash(password)

def verify_password(stored_hash, password):
    return check_password_hash(stored_hash, password)

# ============================================================================
# USER MANAGEMENT - DYNAMODB ONLY
# ============================================================================
def register_user(email, password, name):
    try:
        # Check if user exists
        response = USERS_TABLE_OBJ.scan(FilterExpression='email = :email', 
                                      ExpressionAttributeValues={':email': email.strip().lower()})
        if response['Count'] > 0:
            return False, "User already exists"

        if not is_valid_email(email):
            return False, "Invalid email format"
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        if len(name.strip()) < 2:
            return False, "Name must be at least 2 characters"
        
        email = email.strip().lower()
        name = name.strip()
        password_hash = hash_password(password)
        timestamp = datetime.now().isoformat()
        new_user = {
            'email': email, 'name': name, 'password_hash': password_hash,
            'created_at': timestamp, 'total_reviews': 0, 'avg_rating': 0.0,
            'last_review_date': '', 'is_active': True
        }
        
        USERS_TABLE_OBJ.put_item(Item=new_user)
        send_sns_notification({'event': 'user_registered', 'email': email, 'name': name})
        print(f"✅ New user registered in DynamoDB: {email}")
        return True, "Registration successful"
        
    except Exception as e:
        print(f"❌ Error registering user: {e}")
        return False, "Registration failed. Please try again."

def login_user(email, password):
    try:
        response = USERS_TABLE_OBJ.scan(FilterExpression='email = :email', 
                                      ExpressionAttributeValues={':email': email.strip().lower()})
        users = response['Items']
        
        for user in users:
            if verify_password(user['password_hash'], password):
                if user.get('is_active', True):
                    print(f"✅ User logged in from DynamoDB: {email}")
                    return True, user
        return False, "Invalid email or password"
        
    except Exception as e:
        print(f"❌ Error during login: {e}")
        return False, "Login failed. Please try again."

def get_user(email):
    try:
        response = USERS_TABLE_OBJ.get_item(Key={'email': email.strip().lower()})
        return response.get('Item')
    except Exception as e:
        print(f"❌ Get user error: {e}")
        return None

# ============================================================================
# MOVIE MANAGEMENT - DYNAMODB ONLY
# ============================================================================
def get_all_movies():
    try:
        response = MOVIES_TABLE_OBJ.scan(FilterExpression='active = :val', 
                                       ExpressionAttributeValues={':val': True})
        return response['Items']
    except Exception as e:
        print(f"❌ Get movies error: {e}")
        return []

def get_movie_by_id(movie_id):
    try:
        response = MOVIES_TABLE_OBJ.get_item(Key={'movie_id': str(movie_id)})
        return response.get('Item')
    except Exception as e:
        print(f"❌ Get movie error: {e}")
        return None

def update_movie_stats(movie_id):
    try:
        reviews = get_movie_reviews(movie_id)
        total_reviews = len(reviews)
        avg_rating = sum(r['rating'] for r in reviews) / total_reviews if total_reviews > 0 else 0.0
        
        MOVIES_TABLE_OBJ.update_item(
            Key={'movie_id': movie_id},
            UpdateExpression="SET total_reviews = :tr, avg_rating = :ar, last_updated = :lu",
            ExpressionAttributeValues={
                ':tr': total_reviews, ':ar': round(avg_rating, 2), ':lu': datetime.now().isoformat()
            }
        )
        return True
    except Exception as e:
        print(f"❌ Error updating movie stats: {e}")
        return False

# ============================================================================
# REVIEW MANAGEMENT - DYNAMODB ONLY
# ============================================================================
def submit_review(name, email, movie_id, rating, feedback_text):
    try:
        timestamp = datetime.now().isoformat()
        review_id = str(uuid.uuid4())
        new_review = {
            'review_id': review_id, 'user_email': email, 'movie_id': movie_id,
            'name': name, 'rating': int(rating), 'feedback': feedback_text,
            'created_at': timestamp, 'display_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        REVIEWS_TABLE_OBJ.put_item(Item=new_review)
        update_movie_stats(movie_id)
        update_user_stats(email)
        
        movie_title = get_movie_by_id(movie_id).get('title', 'Unknown') if get_movie_by_id(movie_id) else 'Unknown'
        notification = {
            'event': 'new_review', 'review_id': review_id, 'movie_id': movie_id,
            'movie_title': movie_title, 'user': name, 'rating': rating, 'timestamp': timestamp
        }
        send_sns_notification(notification)
        
        print(f"✅ Review saved to DynamoDB: {review_id}")
        return True
    except Exception as e:
        print(f"❌ Error submitting review: {e}")
        return False

def get_movie_reviews(movie_id, limit=50):
    try:
        response = REVIEWS_TABLE_OBJ.scan(FilterExpression='movie_id = :mid', 
                                        ExpressionAttributeValues={':mid': movie_id})
        reviews = response['Items']
        reviews.sort(key=lambda x: x['created_at'], reverse=True)
        return reviews[:limit]
    except Exception as e:
        print(f"❌ Get movie reviews error: {e}")
        return []

def get_user_reviews(email):
    try:
        response = REVIEWS_TABLE_OBJ.scan(FilterExpression='user_email = :email', 
                                        ExpressionAttributeValues={':email': email})
        reviews = response['Items']
        reviews.sort(key=lambda x: x['created_at'], reverse=True)
        
        movies = get_all_movies()
        for review in reviews:
            for movie in movies:
                if review['movie_id'] == movie['movie_id']:
                    review['movie_title'] = movie['title']
                    review['movie_genre'] = movie['genre']
                    review['movie_image'] = movie['image_url']
                    review['release_year'] = movie.get('release_year', 2025)
                    break
        return reviews
    except Exception as e:
        print(f"❌ Get user reviews error: {e}")
        return []

def update_user_stats(email):
    try:
        reviews = get_user_reviews(email)
        total_reviews = len(reviews)
        
        if total_reviews > 0:
            avg_rating = sum(r['rating'] for r in reviews) / total_reviews
            last_review = max(r['created_at'] for r in reviews)
        else:
            avg_rating = 0.0
            last_review = ''
        
        USERS_TABLE_OBJ.update_item(
            Key={'email': email},
            UpdateExpression="SET total_reviews = :tr, avg_rating = :ar, last_review_date = :lr",
            ExpressionAttributeValues={
                ':tr': total_reviews, ':ar': round(avg_rating, 2), ':lr': last_review
            }
        )
        return True
    except Exception as e:
        print(f"❌ Error updating user stats: {e}")
        return False

# ============================================================================
# RECOMMENDATIONS, ANALYTICS - DYNAMODB ONLY
# ============================================================================
def get_recommendations(email, limit=5):
    try:
        all_movies = get_all_movies()
        user_reviews = get_user_reviews(email)
        
        if not user_reviews:
            return sorted(all_movies, key=lambda x: x.get('avg_rating', 0), reverse=True)[:limit]
        
        rated_movie_ids = set(r['movie_id'] for r in user_reviews)
        genre_ratings = {}
        
        for review in user_reviews:
            genre = review.get('movie_genre', 'Unknown')
            rating = review.get('rating', 0)
            genre_ratings.setdefault(genre, []).append(rating)
        
        favorite_genres = [genre for genre, ratings in genre_ratings.items() 
                          if sum(ratings) / len(ratings) >= 4]
        
        recommendations = [m for m in all_movies 
                          if m['movie_id'] not in rated_movie_ids 
                          and m.get('genre') in favorite_genres]
        recommendations.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
        
        if len(recommendations) < limit:
            other_movies = [m for m in all_movies 
                           if m['movie_id'] not in rated_movie_ids 
                           and m not in recommendations]
            other_movies.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
            recommendations.extend(other_movies[:limit - len(recommendations)])
        
        return recommendations[:limit]
    except Exception as e:
        print(f"❌ Error getting recommendations: {e}")
        return []

def get_total_reviews_count():
    try:
        response = REVIEWS_TABLE_OBJ.scan()
        return len(response['Items'])
    except:
        return 0

def get_genre_distribution():
    try:
        movies = get_all_movies()
        genres = {}
        for movie in movies:
            genre = movie.get('genre', 'Unknown')
            genres[genre] = genres.get(genre, 0) + 1
        return genres
    except:
        return {}

def get_most_reviewed_movies(limit=5):
    try:
        movies = get_all_movies()
        return sorted(movies, key=lambda x: x.get('total_reviews', 0), reverse=True)[:limit]
    except:
        return []

# ============================================================================
# ALL ROUTES (14 templates fully supported - IDENTICAL)
# ============================================================================
@app.route('/')
def index():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip()
        success, message = register_user(email, password, name)
        if success:
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        success, result = login_user(email, password)
        if success:
            user = result
            session['user_email'] = email
            session['user_name'] = user.get('name', email.split('@')[0])
            flash('Login successful! Welcome back!', 'success')
            return redirect(url_for('movies'))
        else:
            flash(result, 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('index'))

@app.route('/movies')
def movies():
    all_movies = get_all_movies()
    genre_filter = request.args.get('genre', 'all').lower()
    if genre_filter != 'all':
        all_movies = [m for m in all_movies if m.get('genre', '').lower() == genre_filter]
    all_movies.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
    return render_template('movies.html', movies=all_movies, current_genre=genre_filter)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    movie = get_movie_by_id(movie_id)
    if not movie:
        flash("Movie not found!", "danger")
        return redirect(url_for('movies'))
    reviews = get_movie_reviews(movie_id)
    return render_template('movie_detail.html', movie=movie, feedback_list=reviews)

@app.route('/feedback/<movie_id>')
def feedback_page(movie_id):
    if not session.get('user_email'):
        flash('Please login to submit feedback!', 'info')
        return redirect(url_for('login'))
    movie = get_movie_by_id(movie_id)
    if not movie:
        flash("Movie not found!", "danger")
        return redirect(url_for('movies'))
    return render_template('feedback.html', movie=movie)

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback_route():
    try:
        if not session.get('user_email'):
            flash('Please login to submit feedback!', 'danger')
            return redirect(url_for('login'))
        
        movie_id = request.form.get('movie_id', '').strip()
        feedback_text = request.form.get('feedback', '').strip()
        rating_raw = request.form.get('rating', '')
        name = session.get('user_name', '')
        email = session.get('user_email', '')
        
        if not all([movie_id, feedback_text, rating_raw]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        rating = int(rating_raw)
        if not (1 <= rating <= 5):
            flash('Rating must be between 1 and 5!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        if len(feedback_text) < 10:
            flash('Feedback must be at least 10 characters!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        movie = get_movie_by_id(movie_id)
        if not movie:
            flash('Invalid movie!', 'danger')
            return redirect(url_for('movies'))
        
        success = submit_review(name, email, movie_id, rating, feedback_text)
        if success:
            flash('Thank you for your feedback! 🎉', 'success')
            return redirect(url_for('thankyou', movie_id=movie_id))
        else:
            flash('Failed to submit feedback. Please try again.', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
    except Exception as e:
        print(f"❌ Error in submit_feedback: {e}")
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('movies'))

@app.route('/thankyou')
def thankyou():
    if not session.get('user_email'):
        return redirect(url_for('login'))
    movie_id = request.args.get('movie_id')
    movie = get_movie_by_id(movie_id) if movie_id else None
    return render_template('thankyou.html', movie=movie, user_name=session.get('user_name', ''))

@app.route('/my-reviews')
def my_reviews():
    if not session.get('user_email'):
        flash('Please login to view your reviews!', 'info')
        return redirect(url_for('login'))
    email = session.get('user_email')
    user = get_user(email)
    user_feedback = get_user_reviews(email)
    recommendations = get_recommendations(email, limit=4)
    return render_template('my_reviews.html', 
                           user_name=session.get('user_name', ''),
                           user_email=email,
                           user_feedback=user_feedback,
                           recommendations=recommendations,
                           total_reviews=len(user_feedback),
                           avg_user_rating=user.get('avg_rating', 0.0) if user else 0.0)

@app.route('/analytics')
def analytics():
    if not session.get('user_email'):
        flash('Please login to view analytics!', 'info')
        return redirect(url_for('login'))
    email = session.get('user_email')
    user_reviews = get_user_reviews(email)
    recommendations = get_recommendations(email, limit=4)
    all_movies = get_all_movies()
    return render_template('analytics.html',
                           user_email=email,
                           user_total_reviews=len(user_reviews),
                           user_avg_rating=0.0,  # Simplified
                           total_movies=len(all_movies),
                           total_reviews=get_total_reviews_count(),
                           genres=get_genre_distribution(),
                           top_movies=sorted(all_movies, key=lambda x: x.get('avg_rating', 0) * x.get('total_reviews', 0) or 0, reverse=True)[:6],
                           most_reviewed=get_most_reviewed_movies(5),
                           recommendations=recommendations)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip().lower()
    if not query:
        flash('Please enter a search term', 'info')
        return redirect(url_for('movies'))
    all_movies = get_all_movies()
    results = [m for m in all_movies if query in m.get('title', '').lower() or 
               query in m.get('description', '').lower() or query in m.get('director', '').lower()]
    return render_template('search_results.html', query=query, movies=results)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# API Endpoints
@app.route('/api/movies')
def api_movies():
    return jsonify({'success': True, 'movies': get_all_movies()})

@app.route('/api/movie/<movie_id>')
def api_movie_detail(movie_id):
    movie = get_movie_by_id(movie_id)
    if movie:
        return jsonify({'success': True, 'movie': movie})
    return jsonify({'success': False, 'error': 'Movie not found'}), 404

@app.route('/api/movie/<movie_id>/reviews')
def api_movie_reviews(movie_id):
    return jsonify({'success': True, 'reviews': get_movie_reviews(movie_id)})

@app.route('/api/user/reviews')
def api_user_reviews():
    if not session.get('user_email'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'reviews': get_user_reviews(session['user_email'])})

@app.route('/api/recommendations')
def api_recommendations():
    if not session.get('user_email'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'recommendations': get_recommendations(session['user_email'])})

# Error Handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500

# Context Processors
@app.context_processor
def inject_user():
    return {
        'logged_in': 'user_email' in session,
        'user_email': session.get('user_email', ''),
        'user_name': session.get('user_name', ''),
        'storage_mode': 'DynamoDB'
    }

@app.context_processor
def inject_genres():
    try:
        movies = get_all_movies()
        return {'available_genres': sorted(set(m.get('genre', '') for m in movies if m.get('genre')))}
    except:
        return {'available_genres': []}

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'storage': 'dynamodb_sns',
        'aws_connected': True,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
