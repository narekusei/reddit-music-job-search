import os
import tkinter as tk
import praw
import threading
from datetime import datetime, timedelta
import webbrowser
import time
import re
import sys

"""
REDDIT API CREDENTIALS - REPLACE THESE WITH YOUR OWN
1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" at the bottom
3. Select "Script", name it (e.g., "RedditSearchTool")
4. Fill in redirect URI: http://localhost:8080
5. Use the generated client_id and client_secret below
"""
CLIENT_ID = ''       # Replace with your client ID (14 characters)
CLIENT_SECRET = ''  # Replace with your client secret
USER_AGENT = 'RedditSearchTool/1.0'   # Can be any string identifying your app

class RedditSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Reddit Music Job Search")
        self.root.geometry("800x600")
        
        # Control variables
        self.search_active = False
        self.found_ids = set()  # Track found posts to avoid duplicates
        self.subreddit_cache = {}  # Cache for subreddit info
        self.keyword_category_cache = {}  # Cache for keyword categories
        
        # Create GUI elements
        self.create_widgets()
        
        # Initialize Reddit client
        try:
            self.reddit = praw.Reddit(
                CLIENT_ID = os.getenv("REDDIT_CLIENT_ID"),
                CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET"),
                USER_AGENT = "windows:reddit-music-job-search:1.0 (by /u/pecheneg69)"
            )
            # Verify connection
            print("Read-only mode:", self.reddit.read_only)
            print("Reddit API:", self.reddit.subreddit("python").display_name)
            print("Subscribers:", self.reddit.subreddit("python").subscribers)
        except Exception as e:
            self.show_error(f"Reddit API Error: {str(e)}\n\nCheck your CLIENT_ID and CLIENT_SECRET!")
    
    def create_widgets(self):
        # Keyword search frame
        search_frame = tk.LabelFrame(self.root, text="Music Job Search Parameters", padx=10, pady=10)
        search_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(search_frame, text="Keywords (separate with ;):").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.keyword_entry = tk.Entry(search_frame, width=50)
        self.keyword_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.keyword_entry.insert(0, "composer;soundtrack;film score;game music;hiring")
        
        # Date range frame
        date_frame = tk.Frame(search_frame)
        date_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        tk.Label(date_frame, text="Start Date (YYYY-MM-DD):").grid(row=0, column=0, sticky="e", padx=5)
        self.start_date_entry = tk.Entry(date_frame, width=15)
        self.start_date_entry.grid(row=0, column=1, padx=5)
        # Default to yesterday
        self.start_date_entry.insert(0, (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"))
        
        tk.Label(date_frame, text="End Date (YYYY-MM-DD):").grid(row=0, column=2, sticky="e", padx=5)
        self.end_date_entry = tk.Entry(date_frame, width=15)
        self.end_date_entry.grid(row=0, column=3, padx=5)
        # Default to today
        self.end_date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        
        # Control buttons
        btn_frame = tk.Frame(search_frame)
        btn_frame.grid(row=0, column=3, padx=10)
        
        self.search_btn = tk.Button(
            btn_frame, 
            text="Search Jobs", 
            command=self.start_search,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold"),
            width=12
        )
        self.search_btn.pack(pady=2)
        
        self.stop_btn = tk.Button(
            btn_frame,
            text="Stop Search",
            command=self.stop_search,
            bg="#FF6347",
            fg="white",
            font=("Arial", 10, "bold"),
            width=12,
            state=tk.DISABLED
        )
        self.stop_btn.pack(pady=2)
        
        # Results frame
        results_frame = tk.LabelFrame(self.root, text="Music Job Postings (appearing in real-time)", padx=10, pady=10)
        results_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Results display with scrollbar
        self.results_text = tk.Text(
            results_frame, 
            wrap=tk.WORD,
            font=("Arial", 10),
            state=tk.DISABLED
        )
        scrollbar = tk.Scrollbar(results_frame, command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=scrollbar.set)
        
        self.results_text.tag_configure("title", foreground="#0066cc", font=("Arial", 10, "bold"))
        self.results_text.tag_configure("link", foreground="#009933", font=("Arial", 10, "italic"))
        self.results_text.tag_configure("date", foreground="#666666", font=("Arial", 9))
        self.results_text.tag_configure("keyword", foreground="#CC0000", font=("Arial", 10, "bold"))
        self.results_text.tag_configure("stats", foreground="#006600", font=("Arial", 9, "bold"))
        self.results_text.tag_configure("source", foreground="#006699", font=("Arial", 9, "italic"))
        self.results_text.tag_configure("info", foreground="#777777", font=("Arial", 8, "italic"))
        self.results_text.tag_configure("job", foreground="#006600", font=("Arial", 10, "bold"))
        
        self.results_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready to search for music composition jobs (1-day default range)")
        status_bar = tk.Label(
            self.root, 
            textvariable=self.status_var,
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def start_search(self):
        """Start search in a separate thread to keep UI responsive"""
        self.clear_results()
        keyword_input = self.keyword_entry.get().strip()
        
        if not keyword_input:
            self.show_error("Please enter at least one search keyword")
            return
            
        # Process multiple keywords
        keywords = [kw.strip() for kw in keyword_input.split(';') if kw.strip()]
        if not keywords:
            self.show_error("No valid keywords found. Use semicolon to separate keywords.")
            return
            
        self.search_active = True
        self.found_ids = set()  # Reset found posts tracking
        self.search_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        # Start search in background thread
        threading.Thread(
            target=self.reddit_style_search,
            args=(keywords,),
            daemon=True
        ).start()
    
    def stop_search(self):
        """Stop an active search"""
        self.search_active = False
        self.status_var.set("Stopping search...")
    
    def parse_date(self, date_str):
        """Parse date string to datetime object"""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format: '{date_str}'. Use YYYY-MM-DD")
    
    def is_valid_subreddit(self, subreddit_name):
        """
        Check if subreddit is valid (SFW and >100 subscribers)
        Uses caching to avoid repeated API calls
        """
        if subreddit_name in self.subreddit_cache:
            return self.subreddit_cache[subreddit_name]
        
        try:
            # Get subreddit info
            subreddit = self.reddit.subreddit(subreddit_name)
            # Force fetch to get actual data
            _ = subreddit.id
            
            is_valid = (
                not subreddit.over18 and  # Not NSFW
                subreddit.subscribers > 100 and  # More than 100 subscribers
                subreddit.public_description != ""  # Not quarantined or private
            )
            
            self.subreddit_cache[subreddit_name] = is_valid
            return is_valid
        except:
            self.subreddit_cache[subreddit_name] = False
            return False
    
    def normalize_keyword(self, keyword):
        """Normalize keyword for consistent processing"""
        # Convert to lowercase and remove special characters
        return re.sub(r'[^\w\s]', '', keyword.lower()).strip()
    
    def get_music_job_subreddits(self, keywords):
        """
        Specialized function to find subreddits relevant to music composition jobs
        """
        music_job_subs = set()
        normalized_keywords = [self.normalize_keyword(kw) for kw in keywords]
        
        # Always include these core music job subreddits
        core_music_subs = [
            'composer', 'MusicJobs', 'GameAudio', 'GameMusic', 'FilmMusic', 
            'MusicProduction', 'WeAreTheMusicMakers', 'sounddesign', 'AudioJobs'
        ]
        
        # Check which core subreddits are valid
        for sub in core_music_subs:
            if self.is_valid_subreddit(sub):
                music_job_subs.add(sub)
        
        # Look for additional relevant subreddits based on keywords
        for kw in normalized_keywords:
            if not kw:
                continue
                
            # Search for subreddits with keyword in name (limit to 5 results)
            try:
                # Fixed: search_by_name doesn't take limit parameter
                # Instead, we convert to list and slice
                name_results = list(self.reddit.subreddits.search_by_name(kw))[:5]
                
                for subreddit in name_results:
                    if self.is_valid_subreddit(subreddit.display_name):
                        music_job_subs.add(subreddit.display_name)
            except Exception as e:
                print(f"Error searching subreddits for '{kw}': {str(e)}")
                continue
            
            # Additional context-based additions for music jobs
            if any(term in kw for term in ['film', 'movie', 'tv', 'cinema', 'score', 'soundtrack']):
                music_job_subs.update(['FilmScoring', 'filmmakers', 'Screenwriting'])
            
            if any(term in kw for term in ['game', 'gaming', 'video game', 'indie game']):
                music_job_subs.update(['GameDev', 'IndieGaming', 'gamedevjobs'])
            
            if any(term in kw for term in ['hire', 'hiring', 'job', 'freelance', 'contract', 'work', 'looking for']):
                music_job_subs.update(['forhire', 'Jobbit', 'Freelance'])
            
            if any(term in kw for term in ['music', 'compose', 'composition', 'composer', 'sound', 'audio']):
                music_job_subs.update(['musictheory', 'musicians', 'audioengineering'])
        
        # Add some general job subreddits that might have music listings
        if any(term in " ".join(normalized_keywords) for term in ['hire', 'job', 'work', 'freelance']):
            music_job_subs.update(['forhire', 'Jobbit', 'Freelance', 'Jobs'])
        
        # Remove any duplicates and return
        return list(music_job_subs)
    
    def is_job_posting(self, title, selftext):
        """
        Determine if a post is likely a job posting
        """
        title = title.lower()
        selftext = selftext.lower()
        
        # Job-related keywords
        job_indicators = [
            'hire', 'hiring', 'looking for', 'need', 'wanted', 'freelance', 
            'contract', 'job', 'opportunity', 'position', 'work', 'collaborate',
            'collaboration', 'commission', 'paid', '$', 'rate', 'budget'
        ]
        
        # Check title for job indicators
        title_match = any(indicator in title for indicator in job_indicators)
        
        # Check text for job indicators (more thorough)
        text_match = any(indicator in selftext for indicator in job_indicators)
        
        # Also check for common job post structures
        structure_match = (
            ('please apply' in selftext or 'apply here' in selftext) or
            ('budget' in selftext and ('composer' in selftext or 'musician' in selftext)) or
            ('rate' in selftext and '$' in selftext) or
            ('timeline' in selftext and 'deliverables' in selftext)
        )
        
        return title_match or text_match or structure_match
    
    def reddit_style_search(self, keywords):
        """Perform search focused specifically on music job postings"""
        try:
            # Validate dates
            start_date = self.parse_date(self.start_date_entry.get())
            end_date = self.parse_date(self.end_date_entry.get())
            
            if start_date > end_date:
                self.root.after(0, lambda: self.show_error("Start date must be before end date"))
                return
                
            # Convert to Unix timestamps
            start_ts = int(start_date.timestamp())
            end_ts = int(end_date.timestamp())
            
            # Get music job-specific subreddits
            relevant_subs = self.get_music_job_subreddits(keywords)
            
            # Show how many relevant communities we found
            self.root.after(0, lambda: self.status_var.set(
                f"Searching in {len(relevant_subs)} music job communities..."
            ))
            
            # Track statistics
            total_checked = 0
            matches_found = 0
            direct_matches = 0
            global_matches = 0
            
            # First phase: Search in music job-specific subreddits
            if relevant_subs and self.search_active:
                # Create search query
                query = " OR ".join(f'"{kw}"' for kw in keywords)
                
                for i, subreddit_name in enumerate(relevant_subs):
                    if not self.search_active:
                        break
                        
                    try:
                        # Check if this subreddit is valid
                        if not self.is_valid_subreddit(subreddit_name):
                            continue
                            
                        # Update status
                        self.root.after(0, lambda sub=subreddit_name, idx=i+1: 
                            self.status_var.set(f"Searching r/{sub} ({idx}/{len(relevant_subs)})..."))
                        
                        # Search this specific subreddit
                        subreddit = self.reddit.subreddit(subreddit_name)
                        for submission in subreddit.search(
                            query,
                            sort="new",
                            params={'syntax': 'lucene', 't': 'all'}
                        ):
                            if not self.search_active:
                                break
                                
                            # Skip if we've already seen this post
                            if submission.id in self.found_ids:
                                continue
                                
                            # Skip if outside date range
                            if submission.created_utc < start_ts or submission.created_utc > end_ts:
                                continue
                                
                            # Additional check: is this actually a job posting?
                            if not self.is_job_posting(submission.title, submission.selftext):
                                continue
                                
                            # Add to found IDs to prevent duplicates
                            self.found_ids.add(submission.id)
                            
                            # Display the result immediately
                            self.add_result(
                                submission, 
                                keywords, 
                                matches_found + 1,
                                f"From r/{subreddit_name} (music job community)"
                            )
                            matches_found += 1
                            direct_matches += 1
                            total_checked += 1
                            
                            # Small delay to be nice to Reddit
                            time.sleep(0.15)
                            
                    except Exception as e:
                        # Skip problematic subreddits
                        continue
            
            # Second phase: Broader search if we need more results
            if self.search_active and matches_found < 20:  # Get more results if needed
                self.root.after(0, lambda: self.status_var.set("Expanding search to broader communities..."))
                
                # Create search query for multiple keywords
                query = " OR ".join(f'"{kw}"' for kw in keywords)
                
                # Search in additional subreddits that might have job postings
                potential_job_subs = [
                    'forhire', 'Jobbit', 'Freelance', 'Jobs', 'musicians', 
                    'GameDev', 'FilmMakers', 'IndieDev', 'DesignJobs'
                ]
                
                for subreddit_name in potential_job_subs:
                    if not self.search_active or matches_found >= 30:
                        break
                        
                    if not self.is_valid_subreddit(subreddit_name):
                        continue
                    
                    try:
                        # Update status
                        self.root.after(0, lambda sub=subreddit_name: 
                            self.status_var.set(f"Checking r/{sub} for job postings..."))
                        
                        # Search this subreddit
                        subreddit = self.reddit.subreddit(subreddit_name)
                        for submission in subreddit.search(
                            query,
                            sort="new",
                            params={'syntax': 'lucene', 't': 'all'}
                        ):
                            if not self.search_active or matches_found >= 30:
                                break
                                
                            # Skip if we've already seen this post
                            if submission.id in self.found_ids:
                                continue
                                
                            # Skip if outside date range
                            if submission.created_utc < start_ts or submission.created_utc > end_ts:
                                continue
                                
                            # Additional check: is this actually a job posting?
                            if not self.is_job_posting(submission.title, submission.selftext):
                                continue
                                
                            # Add to found IDs to prevent duplicates
                            self.found_ids.add(submission.id)
                            
                            # Display the result immediately
                            self.add_result(
                                submission, 
                                keywords, 
                                matches_found + 1,
                                f"From r/{subreddit_name} (general job community)"
                            )
                            matches_found += 1
                            global_matches += 1
                            total_checked += 1
                            
                            # Update status periodically
                            if total_checked % 5 == 0:
                                status_msg = f"Found {matches_found} job postings | {direct_matches} from music communities"
                                self.root.after(0, lambda msg=status_msg: self.status_var.set(msg))
                            
                            # Small delay
                            time.sleep(0.2)
                            
                    except Exception as e:
                        continue
            
            # Final status
            if matches_found == 0:
                self.root.after(0, lambda: self.status_var.set("No music job postings found - try different keywords"))
            else:
                final_msg = f"Found {matches_found} music job postings | {direct_matches} from music communities"
                self.root.after(0, lambda: self.status_var.set(final_msg))
            
        except ValueError as e:
            self.root.after(0, lambda: self.show_error(f"Date Error: {str(e)}"))
        except Exception as e:
            self.root.after(0, lambda: self.show_error(f"Search Error: {str(e)}"))
        finally:
            self.root.after(0, self.search_complete)
    
    def add_result(self, post, keywords, result_num, source_info):
        """Add a single result to the display in real-time"""
        # Format date
        post_date = datetime.fromtimestamp(post.created_utc).strftime("%Y-%m-%d %H:%M")
        
        # Insert result
        self.results_text.config(state=tk.NORMAL)
        
        # Insert title as job posting
        self.results_text.insert(tk.END, f"{result_num}. 🎵 JOB POSTING: {post.title}\n", "job")
        
        # Insert metadata
        self.results_text.insert(tk.END, f"   Posted: {post_date} | r/{post.subreddit} | ", "date")
        self.results_text.insert(tk.END, f"Score: {post.score} | ", "date")
        self.results_text.insert(tk.END, f"Comments: {post.num_comments}\n", "date")
        
        # Insert source info
        self.results_text.insert(tk.END, f"   🌐 {source_info}\n", "source")
        
        # Create clickable link
        link = f"https://www.reddit.com{post.permalink}"
        self.results_text.insert(tk.END, "   ▶ View Job Posting\n", "link")
        
        # Make link clickable
        self.results_text.tag_bind(
            f"link{result_num}", 
            "<Button-1>", 
            lambda e, url=link: webbrowser.open(url)
        )
        self.results_text.tag_add(f"link{result_num}", f"{self.results_text.index(tk.END)}-2 lines", tk.END)
        
        # Show which keywords were found
        found_keywords = []
        post_text = f"{post.title} {post.selftext}".lower()
        for kw in keywords:
            if self.normalize_keyword(kw) in post_text:
                found_keywords.append(kw)
        
        if found_keywords:
            self.results_text.insert(tk.END, f"   🔑 Keywords matched: {', '.join(found_keywords)}\n", "date")
        
        self.results_text.insert(tk.END, "\n")
        
        # Auto-scroll to the bottom
        self.results_text.see(tk.END)
        self.results_text.config(state=tk.DISABLED)
    
    def clear_results(self):
        """Clear previous search results"""
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.config(state=tk.DISABLED)
    
    def show_error(self, message):
        """Display error message in results area"""
        self.clear_results()
        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, f"ERROR: {message}\n\n", "error")
        self.results_text.tag_configure("error", foreground="red", font=("Arial", 10, "bold"))
        self.results_text.config(state=tk.DISABLED)
        self.search_active = False
        self.search_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
    
    def search_complete(self):
        """Reset UI after search completes"""
        self.search_active = False
        self.search_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

if __name__ == "__main__":
    # Verify credentials are set
    if CLIENT_ID == 'YOUR_CLIENT_ID' or CLIENT_SECRET == 'YOUR_CLIENT_SECRET':
        print("="*60)
        print("ERROR: Reddit API credentials not configured!")
        print("1. Create a Reddit app at https://www.reddit.com/prefs/apps")
        print("2. Replace CLIENT_ID and CLIENT_SECRET in the code")
        print("="*60)
        sys.exit(1)
    
    root = tk.Tk()
    app = RedditSearchApp(root)
    root.mainloop()