from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import datetime
import sqlite3
import os
import re
import json
from json import JSONDecodeError

# Flask aplikācijas inicializācija
app = Flask(__name__)

# Aplikācijas konfigurācija
app.config['SECRET_KEY'] = 'a1b2c3d4e5f678901q34x67890abcdefa1b2c3d4e5f6789012e4567890abcdef'  # Slepenā atslēga sesiju šifrēšanai
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chatbot.db'  # SQLite datubāzes atrašanās vieta
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Atslēdz SQLAlchemy brīdinājumus

# Datubāzes inicializācija
db = SQLAlchemy(app)


# Datubāzes modeļi
class User(db.Model):
    """Lietotāju tabulas modelis"""
    id = db.Column(db.Integer, primary_key=True)  # Unikāls lietotāja ID
    username = db.Column(db.String(80), unique=True, nullable=False)  # Lietotājvārds
    password = db.Column(db.String(200), nullable=False)  # Hešēta parole
    registration_ip = db.Column(db.String(45), nullable=False)  # IP adrese reģistrācijas brīdī
    registration_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)  # Reģistrācijas datums
    chats = db.relationship('Chat', backref='user', lazy=True)  # Saite uz lietotāja čatiem
    login_logs = db.relationship('LoginLog', backref='user', lazy=True)  # Saite uz pieteikšanās žurnālu


class LoginLog(db.Model):
    """Pieteikšanās žurnāla tabulas modelis"""
    id = db.Column(db.Integer, primary_key=True)  # Unikāls ieraksta ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Ārējā atslēga uz lietotāju
    login_time = db.Column(db.DateTime, default=datetime.datetime.utcnow)  # Pieteikšanās laiks
    ip_address = db.Column(db.String(45), nullable=False)  # IP adrese pieteikšanās brīdī


class Chat(db.Model):
    """Čatu tabulas modelis"""
    id = db.Column(db.Integer, primary_key=True)  # Unikāls čata ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Ārējā atslēga uz lietotāju
    title = db.Column(db.String(100), default="Jauns čats", nullable=False)  # Čata nosaukums
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)  # Čata izveidošanas laiks
    messages = db.relationship('Message', backref='chat', lazy=True)  # Saite uz čata ziņojumiem


class Message(db.Model):
    """Ziņojumu tabulas modelis"""
    id = db.Column(db.Integer, primary_key=True)  # Unikāls ziņojuma ID
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)  # Ārējā atslēga uz čatu
    role = db.Column(db.String(10), nullable=False)  # Ziņojuma tips: 'user' vai 'assistant'
    content = db.Column(db.Text, nullable=False)  # Ziņojuma saturs
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)  # Ziņojuma laiks
    model = db.Column(db.String(100), nullable=True)  # Izmantotā modeļa nosaukums


# Datubāzes tabulu izveide
with app.app_context():
    db.create_all()  # Izveido visas tabulas, ja tās neeksistē

# LM Studio API konfigurācija (lokālais serveris)
LM_STUDIO_API = "http://127.0.0.1:1234"

# Aktīvo ģenerāciju sekošana (čata ID -> True/False)
active_generations = {}

# Funkcija pieejamo modeļu pārbaudei LM Studio
def get_available_models():
    """
    Iegūst pieejamo modeļu sarakstu no LM Studio API
    Atgriež: saraksts ar modeļiem vai tukšs saraksts kļūdas gadījumā
    """
    try:
        response = requests.get(f"{LM_STUDIO_API}/v1/models")
        if response.status_code == 200:
            return response.json()["data"]
        return []
    except:
        # Ja nav iespējams savienoties ar API, atgriež tukšu sarakstu
        return []


# Funkcija lietotāja IP adreses iegūšanai
def get_client_ip():
    """
    Iegūst klienta IP adresi, ņemot vērā proxy serverus
    Atgriež: IP adrese kā string
    """
    # Pārbauda, vai ir proxy headers
    if request.environ.get('HTTP_X_FORWARDED_FOR') is not None:
        return request.environ['HTTP_X_FORWARDED_FOR']
    # Ja nav proxy, izmanto tiešo IP
    return request.remote_addr

def generate_chat_title(first_message, model_id):
    """
    Ģenerē čata nosaukumu, pamatojoties uz pirmo ziņojumu
    Parametri:
        first_message: pirmais ziņojums čatā
        model_id: modeļa ID, kas tiks izmantots nosaukuma ģenerēšanai
    Atgriež: ģenerēto nosaukumu vai saīsināto ziņojumu
    """
    # Ja nav norādīts modelis, izmanto ziņojuma sākumu
    if not model_id or model_id.strip() == "":
        return first_message[:50] + "..."
    
    try:
        # API pieprasījuma URL
        api_url = f"{LM_STUDIO_API}/v1/chat/completions"
        
        # Pieprasījuma dati nosaukuma ģenerēšanai
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": "Ģenerē īsu nosaukumu lietotāja valodā, pamatojoties uz ziņojumu. Dod tikai 1-2 vārdus kā atbildi, bez pēdiņām."},
                {"role": "user", "content": f"Ziņojums: {first_message}"}
            ],
            "temperature": 0.7,  # Kreativitātes līmenis
            "max_tokens": 20     # Maksimālais tokenu skaits
        }

        # Sūta pieprasījumu uz API
        response = requests.post(api_url, json=payload, timeout=15)
        response.raise_for_status()

        # Apstrādā atbildi
        title_data = response.json()
        title_text = title_data['choices'][0]['message']['content'].strip('"')
        
        # Noņem "Title:" prefiksu, ja tas ir
        title_text = re.sub(r'^Title:?\s*', '', title_text, flags=re.IGNORECASE)
        print(f"Jauns ģenerētais nosaukums: '{title_text}'")
        return title_text

    except requests.exceptions.RequestException as e:
        print(f"HTTP kļūda nosaukuma ģenerēšanas laikā: {e}")
        return first_message[:50] + "..."
    except (KeyError, JSONDecodeError) as e:
        print(f"JSON kļūda nosaukuma apstrādē: {e}")
        return first_message[:50] + "..."
    except Exception as e:
        print(f"Nezināma kļūda generate_chat_title funkcijā: {e}")
        return first_message[:50] + "..."

# Aplikācijas maršruti (routes)

@app.route('/')
def index():
    """
    Galvenā lapa - pārvirza uz čatu, ja lietotājs ir pieteicies
    """
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('chat'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Lietotāja reģistrācijas lapa
    GET: parāda reģistrācijas formu
    POST: apstrādā reģistrācijas datus
    """
    if request.method == 'POST':
        # Iegūst datus no formas
        username = request.form.get('username')
        password = request.form.get('password')
        ip_address = get_client_ip()

        # Pārbauda, vai no šīs IP jau ir reģistrēts lietotājs
        existing_ip = User.query.filter_by(registration_ip=ip_address).first()
        if existing_ip:
            flash('Jūs jau esat reģistrējies! Problēmu gadījumā sazinieties ar administratoru: LocaLLM@darkweb.onion')
            return redirect(url_for('register'))

        # Pārbauda, vai lietotājvārds jau eksistē
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Lietotājs ar šādu lietotājvārdu jau eksistē.')
            return redirect(url_for('register'))

        # Izveido jaunu lietotāju
        hashed_password = generate_password_hash(password)  # Hešē paroli
        new_user = User(username=username, password=hashed_password, registration_ip=ip_address)
        db.session.add(new_user)
        db.session.commit()

        flash('Reģistrācija veiksmīga. Tagad varat pieteikties.')
        return redirect(url_for('login'))

    # GET pieprasījums - parāda reģistrācijas formu
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Lietotāja pieteikšanās lapa
    GET: parāda pieteikšanās formu
    POST: apstrādā pieteikšanās datus
    """
    if request.method == 'POST':
        # Iegūst datus no formas
        username = request.form.get('username')
        password = request.form.get('password')

        # Meklē lietotāju datubāzē
        user = User.query.filter_by(username=username).first()

        # Pārbauda lietotājvārdu un paroli
        if user and check_password_hash(user.password, password):
            # Saglabā lietotāja datus sesijā
            session['user_id'] = user.id
            session['username'] = user.username

            # Ieraksta pieteikšanās žurnālā
            ip_address = get_client_ip()
            login_log = LoginLog(user_id=user.id, ip_address=ip_address)
            db.session.add(login_log)
            db.session.commit()

            return redirect(url_for('chat'))

        # Nepareizi pieteikšanās dati
        flash('Nepareizs lietotājvārds vai parole.')

    # GET pieprasījums - parāda pieteikšanās formu
    return render_template('login.html')

@app.route('/logout')
def logout():
    """
    Lietotāja izrakstīšanās - notīra sesiju
    """
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/chat')
def chat():
    """
    Čata galvenā lapa - parāda pēdējo čatu vai izveido jaunu
    """
    # Pārbauda, vai lietotājs ir pieteicies
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Iegūst lietotāja čatus
    user_chats = Chat.query.filter_by(user_id=session['user_id']).order_by(Chat.created_at.desc()).all()
    models = get_available_models()

    # Ja nav čatu, izveido jaunu
    if not user_chats:
        new_chat = Chat(user_id=session['user_id'])
        db.session.add(new_chat)
        db.session.commit()
        return render_template('chat.html', chats=user_chats, current_chat=new_chat, messages=[], models=models)
    else:
        # Pārvirza uz pēdējo čatu
        latest_chat = user_chats[0]
        return redirect(url_for('view_chat', chat_id=latest_chat.id))


@app.route('/chat/<int:chat_id>')
def view_chat(chat_id):
    """
    Konkrēta čata skatīšana
    Parametri:
        chat_id: čata ID
    """
    # Pārbauda pieteikšanos
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Iegūst čatu
    chat = Chat.query.get_or_404(chat_id)

    # Pārbauda, vai čats pieder lietotājam
    if chat.user_id != session['user_id']:
        return redirect(url_for('chat'))

    # Iegūst čata ziņojumus un pieejamos modeļus
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.timestamp).all()
    user_chats = Chat.query.filter_by(user_id=session['user_id']).order_by(Chat.created_at.desc()).all()
    models = get_available_models()

    return render_template('chat.html', chats=user_chats, current_chat=chat, messages=messages, models=models)

@app.route('/create_chat', methods=['POST'])
def create_chat():
    """
    Jauna čata izveide (AJAX pieprasījums)
    Atgriež: JSON ar jaunā čata datiem
    """
    # Pārbauda pieteikšanos
    if 'user_id' not in session:
        return jsonify({'error': 'Nav pieteicies'}), 401

    # Izveido jaunu čatu
    new_chat = Chat(user_id=session['user_id'])
    db.session.add(new_chat)
    db.session.commit()

    return jsonify({
        'id': new_chat.id,
        'title': new_chat.title
    })


@app.route('/send_message', methods=['POST'])
def send_message():
    """
    Ziņojuma sūtīšana (AJAX pieprasījums)
    Saglabā lietotāja ziņojumu datubāzē un ģenerē čata nosaukumu, ja nepieciešams
    """
    # Pārbauda pieteikšanos
    if 'user_id' not in session:
        return jsonify({'error': 'Nav pieteicies'}), 401
    
    # Iegūst datus no pieprasījuma
    data = request.json
    chat_id = data.get('chat_id')
    content = data.get('content')
    model_id = data.get('model')

    print(f"/send_message: chat_id={chat_id}, model_id={model_id}, content='{content[:20]}...'")

    # Pārbauda čata piederību
    chat = Chat.query.get(chat_id)
    if not chat or chat.user_id != session['user_id']:
        return jsonify({'error': 'Nav autorizēts'}), 403

    # Saglabā lietotāja ziņojumu
    user_message = Message(chat_id=chat_id, role='user', content=content)
    db.session.add(user_message)
    db.session.commit()

    # Pārbauda, vai šis ir pirmais ziņojums čatā
    messages_count = Message.query.filter_by(chat_id=chat_id).count()

    if messages_count == 1:
        # Ģenerē čata nosaukumu pirmajam ziņojumam
        try:
            title = generate_chat_title(content, model_id)
            chat.title = title[:97] + "..." if len(title) > 100 else title
            db.session.commit()
            return jsonify({
                'status': 'success',
                'message_id': user_message.id,
                'updated_chat_title': chat.title
            })
        except Exception as e:
            print(f"Nosaukuma ģenerēšanas kļūda: {e}")
            db.session.rollback()

    return jsonify({'status': 'success', 'message_id': user_message.id})

@app.route('/get_chats')
def get_chats():
    """
    Iegūst lietotāja čatu sarakstu (AJAX pieprasījums)
    Atgriež: JSON ar čatu sarakstu
    """
    if 'user_id' not in session:
        return jsonify([])
    
    chats = Chat.query.filter_by(user_id=session['user_id']).order_by(Chat.created_at.desc()).all()
    return jsonify([{'id': chat.id, 'title': chat.title} for chat in chats])

@app.route('/stop_generation', methods=['POST'])
def stop_generation():
    """
    Aptur ģenerācijas procesu konkrētam čatam (AJAX pieprasījums)
    """
    chat_id = request.json.get('chat_id')
    print(f"Pieprasījums apturēt ģenerāciju čatam: {chat_id}")
    
    if chat_id in active_generations:
        active_generations[chat_id] = False
        print(f"Apturēšanas karodziņš uzstādīts čatam: {chat_id}")
    
    return jsonify(success=True)

@app.route('/get_response', methods=['GET'])
def get_response():
    """
    Iegūst AI atbildi (Server-Sent Events)
    Sūta pieprasījumu uz LM Studio un straumē atbildi
    """
    # Pārbauda pieteikšanos
    if 'user_id' not in session:
        return jsonify({'error': 'Nav pieteicies'}), 401

    # Iegūst parametrus
    chat_id = request.args.get('chat_id')
    model_id = request.args.get('model')

    # Pārbauda čata piederību
    chat = Chat.query.get(chat_id)
    if not chat or chat.user_id != session['user_id']:
        return jsonify({'error': 'Nav autorizēts'}), 403

    # Iegūst čata vēsturi
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.timestamp).all()
    history = [{"role": msg.role, "content": msg.content} for msg in messages]

    try:
        # Pieprasījuma dati LM Studio API
        data = {
            "model": model_id,
            "messages": history,
            "stream": True,      # Straumēšanas režīms
            "temperature": 0.6,  # Kreativitātes līmenis
            "max_tokens": 2048   # Maksimālais tokenu skaits
        }

        def generate():
            """
            Ģenerators AI atbildes straumēšanai
            Izmanto Server-Sent Events protokolu
            """
            # Izveido aplikācijas kontekstu ģeneratorā
            with app.app_context():
                assistant_message = None
                full_content = ""
                active_generations[chat_id] = True  # Atzīmē ģenerāciju kā aktīvu
                
                try:
                    # Sūta pieprasījumu uz LM Studio
                    response = requests.post(f"{LM_STUDIO_API}/v1/chat/completions", json=data, stream=True)

                    # Izveido assistenta ziņojumu datubāzē
                    assistant_message = Message(
                        chat_id=chat_id,
                        role='assistant',
                        content="",
                        model=model_id
                    )
                    db.session.add(assistant_message)
                    db.session.commit()
                    message_id = assistant_message.id
                    
                    # Sūta ziņojuma ID klientam
                    yield f'data: {{"message_id": {message_id}}}\n\n'

                    # Apstrādā straumēto atbildi
                    for line in response.iter_lines():
                        # Pārbauda, vai ģenerācija nav apturēta
                        if not active_generations.get(chat_id, True):
                            print(f"Ģenerācija apturēta lietotāja dēļ čatam: {chat_id}")
                            break
                            
                        if line:
                            line_text = line.decode('utf-8').strip()
                            if line_text.startswith('data: '):
                                json_str = line_text[6:]
                                if json_str == '[DONE]':
                                    print(f"Ģenerācija pabeigta no LM Studio čatam: {chat_id}")
                                    break
                                try:
                                    # Parsē JSON un iegūst saturu
                                    json_obj = json.loads(json_str)
                                    content = json_obj['choices'][0]['delta'].get('content', '')
                                    if content:
                                        full_content += content
                                        # Sūta saturu klientam
                                        yield f"data: {json.dumps({'content': content})}\n\n"
                                except JSONDecodeError:
                                    continue

                    # Saglabā pilno atbildi datubāzē
                    if assistant_message:
                        assistant_message.content = full_content
                        db.session.commit()
                        print(f"Assistenta saturs saglabāts datubāzē ziņojumam: {assistant_message.id}")

                    # Paziņo par ģenerācijas pabeigšanu
                    yield f"data: {json.dumps({'done': True})}\n\n"

                except Exception as e:
                    # Kļūdu apstrāde
                    error_message = f"Kļūda atbildes ģenerēšanā: {str(e)}"
                    print(error_message)
                    error_data = json.dumps({'error': error_message}, ensure_ascii=False)
                    yield f"data: {error_data}\n\n"
                    
                    # Saglabā kļūdu ziņojumu datubāzē
                    if assistant_message:
                        assistant_message.content = f"{full_content}\n[Kļūda: {str(e)}]"
                        db.session.commit()

                finally:
                    # Notīra aktīvo ģenerāciju
                    active_generations.pop(chat_id, None)
                    print(f"Ģenerācijas apstrāde pabeigta čatam: {chat_id}, aktīvās ģenerācijas: {active_generations}")

        # Atgriež Server-Sent Events atbildi
        response = app.response_class(generate(), mimetype='text/event-stream')
        response.headers.add('Cache-Control', 'no-cache')
        response.headers.add('Connection', 'keep-alive')
        return response

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/models')
def models():
    """
    Atgriež pieejamo modeļu sarakstu (AJAX pieprasījums)
    """
    models = get_available_models()
    return jsonify(models)


@app.route('/update_chat_title', methods=['POST'])
def update_chat_title():
    """
    Atjaunina čata nosaukumu (AJAX pieprasījums)
    """
    # Pārbauda pieteikšanos
    if 'user_id' not in session:
        return jsonify({'error': 'Nav pieteicies'}), 401

    # Iegūst datus
    data = request.json
    chat_id = data.get('chat_id')
    new_title = data.get('title')

    # Pārbauda čata piederību
    chat = Chat.query.get(chat_id)
    if not chat or chat.user_id != session['user_id']:
        return jsonify({'error': 'Nav autorizēts'}), 403

    # Atjaunina nosaukumu
    chat.title = new_title
    db.session.commit()

    return jsonify({'success': True})

@app.route('/delete_chat/<int:chat_id>', methods=['POST'])
def delete_chat(chat_id):
    """
    Dzēš čatu un visus tā ziņojumus
    Parametri:
        chat_id: čata ID
    """
    # Pārbauda pieteikšanos
    if 'user_id' not in session:
        return jsonify({'error': 'Nav pieteicies'}), 401

    # Pārbauda čata piederību
    chat = Chat.query.get(chat_id)
    if not chat or chat.user_id != session['user_id']:
        return jsonify({'error': 'Nav autorizēts'}), 403

    # Dzēš visus čata ziņojumus
    Message.query.filter_by(chat_id=chat_id).delete()

    # Dzēš čatu
    db.session.delete(chat)
    db.session.commit()

    return jsonify({'success': True})


# Aplikācijas palaišana
if __name__ == '__main__':
    # Palaiž aplikāciju debug režīmā, pieejamu no visām IP adresēm
    app.run(debug=True, host='0.0.0.0', port=5000)