import os
import json
import re
import tempfile
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# =====================================================================
# КОНФИГУРАЦИЯ
# =====================================================================
BASE_DIR = Path(__file__).parent.absolute()
RAW_DIR = BASE_DIR / 'raw'
OUTPUT_DIR = BASE_DIR / 'Documents'
TEMP_DIR = Path(tempfile.gettempdir()) / 'newspaper_chunker'

RAW_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.rtf', '.doc', '.docx'}

# =====================================================================
# ИЗВЛЕЧЕНИЕ ТЕКСТА
# =====================================================================

def extract_text_with_unstructured(input_path):
    """Извлекает ВЕСЬ текст через Unstructured"""
    try:
        from unstructured.partition.auto import partition
        
        print(f"Извлечение текста из: {os.path.basename(input_path)}")
        elements = partition(filename=input_path, strategy="auto", languages=["rus"])
        
        all_text = []
        for el in elements:
            text = str(el).strip()
            if text:
                all_text.append(text)
        
        full_text = '\n'.join(all_text)
        print(f"✓ Извлечено {len(full_text)} символов")
        return full_text
        
    except Exception as e:
        print(f"Ошибка Unstructured: {e}")
        return None


def extract_text_txt(file_path):
    """Читает текстовый файл"""
    try:
        with open(file_path, 'rb') as f:
            raw = f.read()
        for enc in ['utf-8', 'cp1251', 'cp866']:
            try:
                text = raw.decode(enc)
                if text and len(text.strip()) > 10:
                    return text
            except:
                continue
    except Exception as e:
        print(f"Ошибка чтения: {e}")
    return None


# =====================================================================
# НОВЫЙ АЛГОРИТМ: ВЕСЬ ТЕКСТ, МИНИМУМ РАЗБИЕНИЙ
# =====================================================================

def clean_text(text):
    """Минимальная очистка текста"""
    # Удаляем номера страниц (одинокие цифры)
    text = re.sub(r'\n\s*\d{1,3}\s*\n', '\n', text)
    
    # Склеиваем слова с переносами
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
    
    # Объединяем одиночные переносы строк внутри абзацев
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    
    # Убираем множественные пробелы
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Убираем слишком много пустых строк
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def is_major_headline(line):
    """
    Определяет ЯВНЫЙ заголовок статьи.
    Очень строгие критерии — только явные заголовки.
    """
    line = line.strip()
    
    if not line or len(line) < 10 or len(line) > 120:
        return False
    
    # Не URL, не номер страницы
    if re.match(r'^(www\.|http|\d+\s*$)', line):
        return False
    
    # Должен начинаться с заглавной буквы
    if not line[0].isupper():
        return False
    
    # Минимум 2 слова
    words = line.split()
    if len(words) < 2:
        return False
    
    # ЯВНЫЕ признаки заголовка (нужно 2 или более):
    signals = 0
    
    # 1. Весь текст ЗАГЛАВНЫМИ буквами (РУБРИКА)
    if line.isupper():
        signals += 3
    
    # 2. Каждое слово с заглавной буквы (Title Case)
    if all(w[0].isupper() for w in words):
        signals += 2
    
    # 3. Заканчивается двоеточием
    if line.endswith(':'):
        signals += 2
    
    # 4. Очень короткий (менее 40 символов)
    if len(line) < 40:
        signals += 1
    
    # 5. Содержит числа в начале (как нумерация разделов)
    if re.match(r'^\d+[\.\)]\s', line):
        signals += 2
    
    # 6. Выделен кавычками
    if line.startswith('«') and line.endswith('»'):
        signals += 2
    
    return signals >= 3


def find_articles(text):
    """
    Разбивает текст на крупные статьи.
    Берёт ВЕСЬ текст, разбивает только по ЯВНЫМ заголовкам.
    """
    lines = text.split('\n')
    
    # Ищем ТОЛЬКО явные заголовки
    headlines = []
    for i, line in enumerate(lines):
        if is_major_headline(line):
            headlines.append({
                'title': line.strip(),
                'index': i
            })
    
    print(f"  Найдено заголовков: {len(headlines)}")
    
    # Если заголовков нет или найден только 1 — весь текст одна статья
    if len(headlines) <= 1:
        cleaned = clean_text(text)
        title = cleaned[:100].rsplit('.', 1)[0] + '.' if '.' in cleaned[:100] else cleaned[:100]
        return [{'title': title, 'content': cleaned}]
    
    # Оставляем заголовки, которые НЕ рядом друг с другом (минимум 5 строк между ними)
    filtered = [headlines[0]]
    for h in headlines[1:]:
        if h['index'] - filtered[-1]['index'] >= 5:
            filtered.append(h)
    
    print(f"  После фильтрации: {len(filtered)} заголовков")
    
    # Формируем статьи
    articles = []
    
    for i, headline in enumerate(filtered):
        start = headline['index']
        
        # Конец статьи — следующий заголовок или конец текста
        if i + 1 < len(filtered):
            end = filtered[i + 1]['index']
        else:
            end = len(lines)
        
        # Собираем ВСЕ строки статьи
        article_lines = []
        for j in range(start, end):
            line = lines[j].strip()
            if line:  # Берём все непустые строки
                article_lines.append(line)
        
        article_text = '\n'.join(article_lines)
        cleaned = clean_text(article_text)
        
        if len(cleaned) > 50:
            articles.append({
                'title': headline['title'],
                'content': cleaned
            })
    
    # Если остался текст до первого заголовка — добавляем
    if filtered and filtered[0]['index'] > 0:
        pre_lines = []
        for j in range(0, filtered[0]['index']):
            line = lines[j].strip()
            if line:
                pre_lines.append(line)
        pre_text = '\n'.join(pre_lines)
        pre_cleaned = clean_text(pre_text)
        if len(pre_cleaned) > 50:
            title = pre_cleaned[:100].rsplit('.', 1)[0] + '.' if '.' in pre_cleaned[:100] else pre_cleaned[:100]
            articles.insert(0, {'title': title, 'content': pre_cleaned})
    
    return articles


# =====================================================================
# HTML ИНТЕРФЕЙС
# =====================================================================

def get_html():
    return '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Газетный чанкер</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:Arial,sans-serif;background:#f0f0f0;padding:20px}
        .container{max-width:1200px;margin:0 auto;background:#fff;padding:20px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.1)}
        h1{color:#333;margin-bottom:20px}
        .upload-area{border:2px dashed #ccc;padding:30px;text-align:center;margin-bottom:20px;border-radius:8px;cursor:pointer}
        .upload-area:hover{border-color:#4CAF50;background:#f8f8f8}
        input[type="file"]{display:none}
        button{padding:10px 20px;border:none;border-radius:4px;cursor:pointer;font-size:14px;margin:5px}
        .btn-process{background:#4CAF50;color:#fff}.btn-process:disabled{background:#ccc;cursor:not-allowed}
        .btn-clear{background:#f44336;color:#fff}.btn-download{background:#2196F3;color:#fff}
        .file-item{background:#f8f8f8;padding:10px;margin-bottom:5px;border-radius:4px;display:flex;justify-content:space-between;align-items:center}
        .remove-btn{background:#ff6b6b;color:#fff;border:none;padding:5px 10px;border-radius:3px;cursor:pointer}
        .progress{display:none;margin-bottom:20px;padding:10px;background:#e3f2fd;border-radius:4px}
        .results{display:none;margin-top:20px}
        .results-summary{background:#e8f5e9;padding:15px;border-radius:4px;margin-bottom:15px}
        .article-card{background:#fafafa;border:1px solid #e0e0e0;border-radius:8px;margin-bottom:20px;overflow:hidden}
        .article-header{background:#1976D2;color:white;padding:15px 20px;font-size:18px;font-weight:bold}
        .article-body{padding:20px;line-height:1.8;color:#333;text-align:justify;white-space:pre-wrap}
        .tabs{display:flex;gap:10px;margin-bottom:20px;border-bottom:2px solid #e0e0e0;padding-bottom:10px}
        .tab{padding:10px 20px;cursor:pointer;border-radius:4px 4px 0 0;background:#f0f0f0;border:none}
        .tab.active{background:#4CAF50;color:#fff}
        .tab-content{display:none}
        .tab-content.active{display:block}
        pre{background:#f4f4f4;padding:15px;border-radius:4px;font-size:12px;max-height:500px;overflow:auto}
    </style>
</head>
<body>
<div class="container">
    <h1>📰 Газетный чанкер</h1>
    
    <div class="upload-area" id="dropZone">
        <p>📁 Перетащите файлы или кликните для выбора</p>
        <p style="color:#999;font-size:14px">PDF, TXT, RTF</p>
        <input type="file" id="fileInput" multiple accept=".pdf,.txt,.rtf">
    </div>
    
    <div id="fileList"></div>
    
    <button class="btn-process" id="processBtn" onclick="processFiles()" disabled>⚙️ Обработать</button>
    <button class="btn-clear" onclick="clearFiles()">🗑️ Очистить</button>
    
    <div class="progress" id="progress"><span id="progressText"></span></div>
    
    <div class="results" id="results">
        <div class="results-summary" id="resultsSummary"></div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('articles')">📄 Статьи</button>
            <button class="tab" onclick="showTab('json')">📋 JSON</button>
        </div>
        
        <div class="tab-content active" id="tabArticles"></div>
        <div class="tab-content" id="tabJson"></div>
        
        <button class="btn-download" onclick="downloadJSON()">📥 JSON</button>
        <button class="btn-download" onclick="downloadTXT()">📥 TXT</button>
    </div>
</div>

<script>
let selectedFiles=[],currentResult=null;
const dz=document.getElementById('dropZone'),fi=document.getElementById('fileInput');
dz.addEventListener('click',()=>fi.click());
dz.addEventListener('dragover',e=>{e.preventDefault();dz.style.borderColor='#4CAF50'});
dz.addEventListener('dragleave',()=>{dz.style.borderColor='#ccc'});
dz.addEventListener('drop',e=>{e.preventDefault();dz.style.borderColor='#ccc';addFiles(e.dataTransfer.files)});
fi.addEventListener('change',e=>{addFiles(e.target.files)});

function addFiles(nf){
    for(let f of nf){
        const e=f.name.split('.').pop().toLowerCase();
        if(['pdf','txt','rtf'].includes(e)&&!selectedFiles.find(x=>x.name===f.name&&x.size===f.size))
            selectedFiles.push(f)
    }
    updateFileList()
}

function updateFileList(){
    const l=document.getElementById('fileList'),b=document.getElementById('processBtn');
    if(!selectedFiles.length){l.innerHTML='';b.disabled=true;return}
    l.innerHTML=selectedFiles.map((f,i)=>`<div class="file-item"><span>📄 ${f.name} (${formatSize(f.size)})</span><button class="remove-btn" onclick="removeFile(${i})">✕</button></div>`).join('');
    b.disabled=false
}

function removeFile(i){selectedFiles.splice(i,1);updateFileList()}
function clearFiles(){selectedFiles=[];currentResult=null;updateFileList();document.getElementById('results').style.display='none';document.getElementById('progress').style.display='none'}
function formatSize(b){return b<1024?b+' B':b<1048576?(b/1024).toFixed(1)+' KB':(b/1048576).toFixed(1)+' MB'}

async function processFiles(){
    if(!selectedFiles.length)return;
    const p=document.getElementById('progress'),pt=document.getElementById('progressText'),r=document.getElementById('results');
    p.style.display='block';r.style.display='none';pt.textContent='⏳ Извлечение статей...';
    const fd=new FormData();selectedFiles.forEach(f=>fd.append('files',f));
    try{
        const resp=await fetch('/process',{method:'POST',body:fd}),data=await resp.json();
        if(data.error){pt.textContent='❌ '+data.error;setTimeout(()=>p.style.display='none',3000);return}
        currentResult=data;displayResults(data);pt.textContent='✅ Готово!';setTimeout(()=>p.style.display='none',2000)
    }catch(e){pt.textContent='❌ Ошибка';setTimeout(()=>p.style.display='none',3000)}
}

function displayResults(d){
    document.getElementById('resultsSummary').innerHTML=`<strong>📊 Результаты</strong><br>Файлов: ${d.files_processed}<br>Статей: ${d.total_chunks}`;
    let h='';
    for(const[fn,fd]of Object.entries(d.results||{})){
        h+=`<h2 style="margin:20px 0 10px">📄 ${fn} (${fd.chunks.length} статей)</h2>`;
        if(fd.chunks){
            fd.chunks.forEach(c=>{
                h+=`<div class="article-card"><div class="article-header">${c.id}. ${esc(c.theme)}</div><div class="article-body">${esc(c.content)}</div></div>`
            })
        }
    }
    document.getElementById('tabArticles').innerHTML=h||'<p>Нет данных</p>';
    document.getElementById('tabJson').innerHTML='<pre>'+esc(JSON.stringify(d,null,2))+'</pre>';
    document.getElementById('results').style.display='block'
}

function showTab(n){
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.tab')[n==='articles'?0:1].classList.add('active');
    document.getElementById(n==='articles'?'tabArticles':'tabJson').classList.add('active')
}

function downloadJSON(){
    if(!currentResult)return;
    const b=new Blob([JSON.stringify(currentResult,null,2)],{type:'application/json'});
    const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='articles.json';a.click()
}

function downloadTXT(){
    if(!currentResult)return;
    let t='';
    for(const[fn,fd]of Object.entries(currentResult.results||{})){
        t+='ФАЙЛ: '+fn+'\\n'+'='.repeat(70)+'\\n\\n';
        (fd.chunks||[]).forEach(c=>{
            t+=`СТАТЬЯ ${c.id}: ${c.theme}\\n`+'-'.repeat(50)+'\\n';
            t+=c.content+'\\n\\n'
        })
    }
    const b=new Blob([t],{type:'text/plain;charset=utf-8'});
    const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='articles.txt';a.click()
}

function esc(s){
    const d=document.createElement('div');d.textContent=s;return d.innerHTML
}
</script>
</body>
</html>'''


# =====================================================================
# HTTP СЕРВЕР
# =====================================================================

class ChunkerHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        if self.path in ['/', '/index.html']:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(get_html().encode('utf-8'))
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/process':
            try:
                content_type = self.headers.get('Content-Type', '')
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                
                files_data = []
                if 'boundary=' in content_type:
                    boundary = content_type.split('boundary=')[1].strip().strip('"')
                    for part in body.split(b'--' + boundary.encode()):
                        if b'Content-Disposition' not in part:
                            continue
                        header_end = part.find(b'\r\n\r\n')
                        if header_end == -1:
                            continue
                        headers = part[:header_end].decode('utf-8', errors='ignore')
                        content = part[header_end + 4:]
                        if content.endswith(b'\r\n'):
                            content = content[:-2]
                        if 'filename=' in headers:
                            fn_match = re.search(r'filename="([^"]+)"', headers)
                            if fn_match:
                                files_data.append((fn_match.group(1), content))
                
                if not files_data:
                    self.send_json({'error': 'Файлы не найдены'})
                    return
                
                results = {}
                total_articles = 0
                
                for filename, file_content in files_data:
                    temp_path = TEMP_DIR / filename
                    with open(temp_path, 'wb') as f:
                        f.write(file_content)
                    
                    try:
                        ext = os.path.splitext(filename)[1].lower()
                        
                        if ext == '.pdf':
                            text = extract_text_with_unstructured(str(temp_path))
                        elif ext in ['.txt', '.rtf']:
                            text = extract_text_txt(str(temp_path))
                        else:
                            continue
                        
                        if text:
                            print(f"Поиск статей в: {filename}")
                            articles = find_articles(text)
                            print(f"  Найдено статей: {len(articles)}")
                            
                            chunks = []
                            for i, article in enumerate(articles, 1):
                                chunks.append({
                                    'id': i,
                                    'theme': article['title'],
                                    'content': article['content']
                                })
                            
                            results[filename] = {
                                'chunks': chunks,
                                'total_chunks': len(chunks)
                            }
                            total_articles += len(chunks)
                    finally:
                        if temp_path.exists():
                            temp_path.unlink()
                
                self.send_json({
                    'files_received': len(files_data),
                    'files_processed': len(results),
                    'total_chunks': total_articles,
                    'results': results
                })
                
            except Exception as e:
                print(f"Ошибка: {e}")
                self.send_json({'error': str(e)})
        else:
            self.send_error(404)
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


def main():
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("  ГАЗЕТНЫЙ ЧАНКЕР — КРУПНЫЕ СТАТЬИ")
    print("=" * 60)
    print(f"  Сервер: http://0.0.0.0:{port}")
    print("=" * 60)
    
    server = HTTPServer(('0.0.0.0', port), ChunkerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен")
        server.server_close()


if __name__ == '__main__':
    main()