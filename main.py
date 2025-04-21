from flask import Flask, request
import os, requests
from tinydb import TinyDB, Query
import datetime

# Initialize databases
db = TinyDB('data.json')
cat_table = db.table('categories')  # stores user custom categories with keywords

token = os.environ['BOT_TOKEN']
API_URL = f"https://api.telegram.org/bot{token}/"

# Default keyword-based categories
CATEGORY_KEYWORDS = {
    'Tasks': ['todo', 'task', 'remind', 'reminder'],
    'Ideas': ['idea', 'think', 'brainstorm'],
    'Journal': ['feel', 'today', 'journal'],
    'Quotes': ['quote', 'wisdom', 'says']
}

def get_main_keyboard():
    return {
        'keyboard': [
            ['/start', '/newcat'],
            ['/categories', '/list'],
            ['/export', '/donate']
        ],
        'resize_keyboard': True,
        'one_time_keyboard': False
    }

def categorize(user_id, text):
    t = text.lower()
    all_categories = CATEGORY_KEYWORDS.copy()
    
    # Get user's custom categories
    user = Query()
    user_rec = cat_table.get(user.user_id == user_id)
    if user_rec and 'categories' in user_rec:
        all_categories.update(user_rec['categories'])
    
    # Check all categories
    for cat, kws in all_categories.items():
        if any(kw in t for kw in kws):
            return cat
    return 'Unsorted'

app = Flask(__name__)

@app.route(f"/{token}", methods=["POST"])
def webhook():
    update = request.get_json()
    
    if 'message' in update:
        msg = update['message']
        cid = msg['chat']['id']
        txt = msg.get('text', '')
        user_id = msg['from']['id']

        if txt.startswith('/start'):
            welcome = (
                "🧠 Welcome to Brain Dump Buddy!\n\n"
                "I help organize your thoughts into categories. Here's how:\n"
                "- Just send me text and I'll auto-categorize it\n"
                "- Use /newcat to create custom categories\n"
                "- Use /categories to see all available categories\n"
                "- Use the buttons below to navigate\n"
            )
            requests.post(API_URL+'sendMessage', json={
                'chat_id': cid,
                'text': welcome,
                'reply_markup': get_main_keyboard()
            })

        elif txt.startswith('/newcat'):
            parts = txt.split(maxsplit=2)
            if len(parts) < 3:
                resp = "Please use: /newcat CategoryName keyword1,keyword2,..."
            else:
                _, name, keywords = parts
                kw_list = [k.strip().lower() for k in keywords.split(',')]
                
                user = Query()
                rec = cat_table.get(user.user_id == user_id)
                
                if rec:
                    cats = rec['categories']
                    cats[name] = kw_list
                    cat_table.update({'categories': cats}, user.user_id == user_id)
                    resp = f"Updated category '{name}' with keywords: {', '.join(kw_list)}"
                else:
                    cat_table.insert({'user_id': user_id, 'categories': {name: kw_list}})
                    resp = f"Created category '{name}' with keywords: {', '.join(kw_list)}"
                
            requests.post(API_URL+'sendMessage', json={
                'chat_id': cid,
                'text': resp,
                'reply_markup': get_main_keyboard()
            })

        elif txt.startswith('/categories'):
            user = Query()
            rec = cat_table.get(user.user_id == user_id)
            custom_cats = rec['categories'].keys() if rec else []
            
            resp = "Default categories:\n" + "\n".join(CATEGORY_KEYWORDS.keys())
            if custom_cats:
                resp += "\n\nYour custom categories:\n" + "\n".join(custom_cats)
            else:
                resp += "\n\nYou have no custom categories yet."
            
            requests.post(API_URL+'sendMessage', json={
                'chat_id': cid,
                'text': resp,
                'reply_markup': get_main_keyboard()
            })

        elif txt.startswith('/list'):
            user = Query()
            entries = db.search((user.user_id == user_id) & user.text.exists())
            resp = "Your entries:\n" + "\n".join(
                f"[{e['category']}] {e['text']}" 
                for e in entries
            ) if entries else "No entries yet!"
            requests.post(API_URL+'sendMessage', json={'chat_id': cid, 'text': resp})

        elif txt.startswith('/export'):
            with open('data.json','rb') as f:
                requests.post(API_URL+'sendDocument', 
                            files={'document': f},
                            data={'chat_id': cid})

        elif txt.startswith('/donate'):
            msg = "Support Brain Dump Buddy! ☕\nhttps://ko-fi.com/YourPage"
            requests.post(API_URL+'sendMessage', json={'chat_id': cid, 'text': msg})

        else:
            # Store and categorize
            cat = categorize(user_id, txt)
            rec = {
                'user_id': user_id,
                'text': txt,
                'timestamp': datetime.datetime.now().isoformat(),
                'category': cat
            }
            doc_id = db.insert(rec)
            
            # Create inline keyboard for category confirmation
            keyboard = {
                'inline_keyboard': [[
                    {'text': 'Change Category', 'callback_data': f'change_{doc_id}'}
                ]]
            }
            
            requests.post(API_URL+'sendMessage', json={
                'chat_id': cid,
                'text': f"Saved under *{cat}*",
                'parse_mode': 'Markdown',
                'reply_markup': keyboard
            })

    elif 'callback_query' in update:
        cq = update['callback_query']
        data = cq['data']
        cid = cq['message']['chat']['id']
        user_id = cq['from']['id']
        
        if data.startswith('change_'):
            doc_id = int(data.split('_')[1])
            entry = db.get(doc_id=doc_id)
            
            if entry and entry['user_id'] == user_id:
                # Get available categories
                user = Query()
                rec = cat_table.get(user.user_id == user_id)
                custom_cats = rec['categories'].keys() if rec else []
                all_cats = list(CATEGORY_KEYWORDS.keys()) + list(custom_cats)
                
                # Create buttons
                buttons = [[{'text': cat, 'callback_data': f'setcat_{doc_id}_{cat}'}]
                         for cat in all_cats]
                buttons.append([{'text': 'Cancel', 'callback_data': f'cancel_{doc_id}'}])
                
                requests.post(API_URL+'editMessageText', json={
                    'chat_id': cid,
                    'message_id': cq['message']['message_id'],
                    'text': 'Select a new category:',
                    'reply_markup': {'inline_keyboard': buttons}
                })
        
        elif data.startswith('setcat_'):
            _, doc_id, new_cat = data.split('_', 2)
            doc_id = int(doc_id)
            db.update({'category': new_cat}, doc_ids=[doc_id])
            
            requests.post(API_URL+'editMessageText', json={
                'chat_id': cid,
                'message_id': cq['message']['message_id'],
                'text': f"✅ Moved to {new_cat} category!"
            })
        
        elif data.startswith('cancel_'):
            requests.post(API_URL+'deleteMessage', json={
                'chat_id': cid,
                'message_id': cq['message']['message_id']
            })

    return 'OK'

@app.route('/')
def home():
    return 'Brain Dump Buddy is running!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
