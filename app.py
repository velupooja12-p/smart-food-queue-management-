from flask import Flask,jsonify,request,send_from_directory
from flask_cors import CORS
from pathlib import Path
import sqlite3,json
from datetime import datetime,date

BASE=Path(__file__).resolve().parent.parent
DB=Path(__file__).with_name('foodcourt.db')
app=Flask(__name__,static_folder=str(BASE/'frontend'),static_url_path='')
CORS(app)

DEFAULTS=[
(1,'Breakfast','07:00','10:00','B',[('Idly',30,1),('Masala Dosa',50,1),('Ven Pongal',40,1),('Medu Vada',35,1),('Poori Masala',45,1)]),
(2,'Morning Break','10:30','11:30','MB',[('Tea',15,1),('Coffee',20,1),('Biscuits',10,1),('Bread Omelette',45,0),('Bun',20,1)]),
(3,'Lunch','12:00','14:00','L',[('Sambar Rice',45,1),('Veg Biryani',70,1),('Curd Rice',40,1),('Rasam Rice',35,1),('Chicken Biryani',100,0)]),
(4,'Evening Break','16:30','18:00','EB',[('Tea',15,1),('Coffee',20,1),('Samosa',20,1),('Bajji/Bonda',25,1),('Sandwich',40,1)]),
(5,'Dinner','19:00','22:00','D',[('Paneer Butter Masala + Roti',80,1),('Veg Kurma + Parotta',70,1),('Dal Fry + Rice',60,1),('Chapati + Sabzi',60,1),('Chicken Chettinad + Parotta',110,0)])]

def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 c=db();c.executescript('CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY,name TEXT,start_time TEXT,end_time TEXT,prefix TEXT);CREATE TABLE IF NOT EXISTS menu(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id INTEGER,name TEXT,price REAL,veg INTEGER);CREATE TABLE IF NOT EXISTS tokens(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id INTEGER,number TEXT,items TEXT,status TEXT,created_at TEXT);')
 if c.execute('SELECT COUNT(*) n FROM sessions').fetchone()['n']==0:
  for sid,n,st,en,p,m in DEFAULTS:
   c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(sid,n,st,en,p))
   for name,price,veg in m:c.execute('INSERT INTO menu(session_id,name,price,veg) VALUES(?,?,?,?)',(sid,name,price,veg))
 c.commit();c.close()
def active(s):
 d=datetime.now();n=d.hour*60+d.minute;h,m=map(int,s['start_time'].split(':'));a=h*60+m;h,m=map(int,s['end_time'].split(':'));b=h*60+m;return a<=n<b
def sd(c,s):
 d=dict(s);d['menu']=[dict(x) for x in c.execute('SELECT name,price,veg FROM menu WHERE session_id=? ORDER BY id',(s['id'],))];return d
@app.get('/')
def home():return send_from_directory(BASE/'frontend','index.html')
@app.get('/api/health')
def health():return jsonify(ok=True)
@app.get('/api/sessions')
def sessions():
 c=db();x=[sd(c,s) for s in c.execute('SELECT * FROM sessions ORDER BY id')];c.close();return jsonify(x)
@app.get('/api/queue/<int:sid>')
def queue(sid):
 c=db();w=c.execute("SELECT * FROM tokens WHERE session_id=? AND status='WAITING' ORDER BY id",(sid,)).fetchall();r=c.execute("SELECT * FROM tokens WHERE session_id=? AND status='READY' ORDER BY id",(sid,)).fetchall();served=c.execute("SELECT COUNT(*) n FROM tokens WHERE session_id=? AND status='SERVED'",(sid,)).fetchone()['n'];c.close()
 def t(x):return {'id':x['id'],'number':x['number'],'items':json.loads(x['items']),'status':x['status']}
 return jsonify(waiting=[t(x) for x in w],ready=[t(x) for x in r],served_count=served,now_serving=t(r[0])['number'] if r else '--')
@app.post('/api/token')
def token():
 d=request.get_json() or {};sid=int(d.get('session_id',0));items=d.get('items',[]);c=db();s=c.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
 if not s or not active(s):c.close();return jsonify(error='Ordering is closed for this session.'),400
 if not items:c.close();return jsonify(error='Select at least one food item.'),400
 today=date.today().isoformat();n=c.execute("SELECT COUNT(*) n FROM tokens WHERE session_id=? AND date(created_at)=?",(sid,today)).fetchone()['n']+1;num=s['prefix']+str(n);created=datetime.now().isoformat(timespec='seconds')
 c.execute('INSERT INTO tokens(session_id,number,items,status,created_at) VALUES(?,?,?,?,?)',(sid,num,json.dumps(items),'WAITING',created));c.commit();ahead=c.execute("SELECT COUNT(*) n FROM tokens WHERE session_id=? AND status='WAITING'",(sid,)).fetchone()['n']-1;c.close()
 return jsonify(token={'number':num},people_ahead=max(0,ahead),estimated_wait=max(0,ahead)*3)
@app.post('/api/queue/<int:sid>/call-next')
def callnext(sid):
 c=db();r=c.execute("SELECT id FROM tokens WHERE session_id=? AND status='WAITING' ORDER BY id LIMIT 1",(sid,)).fetchone()
 if not r:c.close();return jsonify(error='No waiting token'),400
 c.execute("UPDATE tokens SET status='READY' WHERE id=?",(r['id'],));c.commit();c.close();return jsonify(ok=True)
@app.post('/api/token/<int:tid>/status')
def status(tid):
 st=(request.get_json() or {}).get('status')
 if st not in ('WAITING','READY','SERVED','SKIPPED'):return jsonify(error='Invalid status'),400
 c=db();c.execute('UPDATE tokens SET status=? WHERE id=?',(st,tid));c.commit();c.close();return jsonify(ok=True)
@app.put('/api/sessions/<int:sid>')
def edit(sid):
 d=request.get_json() or {};c=db()
 if 'start_time' in d:c.execute('UPDATE sessions SET start_time=?,end_time=? WHERE id=?',(d['start_time'],d['end_time'],sid))
 if 'menu' in d:
  c.execute('DELETE FROM menu WHERE session_id=?',(sid,))
  for m in d['menu']:c.execute('INSERT INTO menu(session_id,name,price,veg) VALUES(?,?,?,?)',(sid,m['name'],float(m['price']),int(bool(m.get('veg',True)))))
 c.commit();c.close();return jsonify(ok=True)
@app.get('/api/analytics')
def analytics():
 c=db();today=date.today().isoformat();total=c.execute('SELECT COUNT(*) n FROM tokens WHERE date(created_at)=?',(today,)).fetchone()['n'];c.close();return jsonify(total_tokens=total)
if __name__=='__main__':
 init();print('Open http://127.0.0.1:5000');app.run(host='127.0.0.1',port=5000,debug=False)
