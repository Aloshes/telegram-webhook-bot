from flask import Flask, request
import os, requests
from tinydb import TinyDB, Query
import datetime

# Initialize databases
db = TinyDB('data.json')
cat_table = db.table('categories')  # stores user custom categories

token = os.environ['BOT_TOKEN']
API_URL = f"https://api.telegram.org/bot{token}/"

# Default keyword-based categories
CATEGORY_KEYWORDS = {
    'Tasks': ['todo', 'task', 'remind', 'reminder'],
    'Ideas': ['idea', 'think', 'brainstorm'],
    'Journal': ['feel', 'today', 'journal'],
    'Quotes': ['quote', 'wisdom', 'says']
}

def categorize(text):
    t = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
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

        # /newcat <name> → add custom category
        if txt.startswith('/newcat '):
            new_cat = txt.split(' ',1)[1].strip()
            user = Query()
            rec = cat_table.get(user.user_id == cid)
            if rec:
                cats = rec['categories']
                if new_cat in cats:
                    resp = f"Category '{new_cat}' already exists."  
                else:
                    cats.append(new_cat)
                    cat_table.update({'categories': cats}, user.user_id == cid)
                    resp = f"Added new category: '{new_cat}'."
            else:
                cat_table.insert({'user_id': cid, 'categories': [new_cat]})
                resp = f"Created and added category: '{new_cat}'."
            requests.post(API_URL+'sendMessage', json={'chat_id':cid,'text':resp})

        # /categories → list default + custom
        elif txt.startswith('/categories'):
            user = Query()
            rec = cat_table.get(user.user_id == cid)
            custom = rec['categories'] if rec else []
            all_cats = list(CATEGORY_KEYWORDS.keys()) + custom
            resp = "Available categories:\n" + "\n".join(all_cats)
            requests.post(API_URL+'sendMessage',json={'chat_id':cid,'text':resp})

        # /list → show stored entries
        elif txt.startswith('/list'):
            user = Query()
            entries = db.search((user.user_id == cid) & user.get('text')
                                & (~user.table_name == 'categories'))
            if not entries:
                resp = "You have no entries yet."
            else:
                resp = '\n'.join(f"[{e['category']}] {e['text']}" for e in entries)
            requests.post(API_URL+'sendMessage', json={'chat_id':cid,'text':resp})

        # /export → download JSON
        elif txt.startswith('/export'):
            with open('data.json','rb') as f:
                requests.post(API_URL+'sendDocument', files={'document':f}, data={'chat_id':cid})

        # /donate → donation link
        elif txt.startswith('/donate'):
            msg = "If you like Brain Dump Buddy, consider a coffee! ☕\nKo-fi: https://ko-fi.com/YourPage"
            requests.post(API_URL+'sendMessage',json={'chat_id':cid,'text':msg})

        else:
            # store and auto-categorize
            cat = categorize(txt)
            rec = {
                'user_id': cid,
                'text': txt,
                'timestamp': msg.get('date', int(datetime.datetime.utcnow().timestamp())),
                'category': cat
            }
            db.insert(rec)
            resp = f"Saved under *{cat}*."
            requests.post(API_URL+'sendMessage',json={'chat_id':cid,'text':resp,'parse_mode':'Markdown'})
    return 'OK'

@app.route('/')
def home():
    return 'Brain Dump Buddy is running'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)))
