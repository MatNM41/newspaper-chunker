import os
import json
import subprocess
import re
import tempfile
from pathlib import Path
from datetime import datetime
from collections import OrderedDict
from http.server import HTTPServer, BaseHTTPRequestHandler

# =====================================================================
# КОНФИГУРАЦИЯ
# =====================================================================
SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.rtf', '.doc', '.docx'}
TEMP_DIR = os.path.join(tempfile.gettempdir(), 'newspaper_chunker')
os.makedirs(TEMP_DIR, exist_ok=True)

# =====================================================================
# ИЗВЛЕЧЕНИЕ ТЕКСТА
# =====================================================================

def extract_text_with_unstructured(input_path):
    """Извлекает текст через Unstructured (как библиотека)"""
    try:
        from unstructured.partition.auto import partition
        
        print(f"Извлечение текста из: {os.path.basename(input_path)}")
        elements = partition(filename=input_path, strategy="auto", languages=["rus"])
        
        text_parts = []
        for el in elements:
            text_parts.append(str(el))
        
        full_text = "\n".join(text_parts)
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
# АЛГОРИТМ ЧАНКИНГА
# =====================================================================

def extract_meaningful_phrases(text):
    """Извлекает значимые фразы (10 категорий)"""
    elements = set()
    
    # 1. ДАТЫ
    date_patterns = [
        r'\d{1,2}\s+(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])\s+\d{4}\s*(?:год[а]?|г\.)?',
        r'\b\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2})\b',
        r'(?:\()?\d{4}(?:\))?\s*(?:год[а]?|г\.|гг\.)?',
        r'\d{4}\s*[–\-]\s*\d{4}',
        r'\b\d{2,4}\s*[-–]\s*[ея]+\s*(?:год[аы]?)?',
        r'(?:XX|XIX|XVIII|XXI)?\s*\d{1,2}[-й]*\s*(?:век[а]?|столети[ея])',
        r'с\s+\d{1,2}\s+по\s+\d{1,2}\s+(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])',
        r'(?:Новый\s+год|Рождество|Пасх[аи]|День\s+Побед[аы]|9\s+мая|23\s+февраля|8\s+марта|1\s+мая|4\s+ноября|12\s+июня)',
        r'\d+[-]?(?:лети[еюя]|летн[яяийего]|годовой|годовщин[аы]|й\s+год)',
        r'(?:весн[аы]|лет[ао]|осен[ьи]|зим[аы])\s+\d{4}',
        r'\d{1,2}[:.]\d{2}',
    ]
    for p in date_patterns:
        for m in re.findall(p, text, re.IGNORECASE):
            m = m.strip()
            if m.lower() not in ['год', 'г.', 'г', 'лет', 'дня', 'для', 'или', 'ещё', 'уже', 'это', 'как', 'что']:
                m = re.sub(r'[()]', '', m).strip()
                if 3 <= len(m) <= 80:
                    elements.add(m)
    
    # 2. ИМЕНА
    for m in re.findall(r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?', text):
        if len(m.split()) <= 3 and not re.search(r'(?:Сегодня|Завтра|Вчера|Как|Что|Это|Для|Или|Уже|Ещё)', m):
            elements.add(m.strip())
    
    # 3. ОРГАНИЗАЦИИ
    for p in [
        r'[«"][^«»"]{3,}[»"]',
        r'(?:ООО|ЗАО|ОАО|ПАО|НКО|АО|ИП)\s*[«"][^«»"]+[»"]?',
        r'(?:Правительство|Администрация|Министерство|Госсовет|Госдума)\s+(?:России|Удмуртии|РФ|города|района)?',
        r'ГКЧП|СНГ|ООН|НАТО|ЕС|БРИКС|КПСС|СССР',
    ]:
        for m in re.findall(p, text, re.IGNORECASE):
            if len(m.strip()) > 3:
                elements.add(m.strip())
    
    # 4. ГЕОГРАФИЯ
    for p in [
        r'г\.\s*[А-ЯЁ][а-яё]+', r'ул\.\s*[А-ЯЁ][а-яё]+',
        r'Советский\s+Союз|Российская\s+Федераци[яи]|Росси[яи]',
        r'Удмурт(?:и[яи]|ской|ия)|Ижевск[аеу]?|Москв[аые]',
    ]:
        for m in re.findall(p, text, re.IGNORECASE):
            if len(m.strip()) > 3:
                elements.add(m.strip())
    
    # 5-10. ОСТАЛЬНЫЕ КАТЕГОРИИ
    for p in [
        r'Ирония\s+судьбы|Джентльмены\s+удачи|Высоцк[а-яё]+|Гагарин[а]?',
        r'калачик\s+за\s+\d+\s+копеек|талоны\s+на\s+(?:масло|водку)|железный\s+занавес|холодная\s+война',
        r'Великая\s+Побед[аы]|дружб[аы]\s+народов|мир\s*[-–]\s*труд\s*[-–]\s*май',
        r'\d+[\s]*(?:миллион|миллиард|тысяч|процент|рубл[еяй]|млрд|млн)',
        r'бюджет|строительство|ремонт|выбор[аы]|СВО|спецопераци[яи]|юбилей|фестиваль|ярмарка',
    ]:
        for m in re.findall(p, text, re.IGNORECASE):
            if len(m.strip()) > 3:
                elements.add(m.strip())
    
    # ФИЛЬТРАЦИЯ
    final = []
    for elem in sorted(list(elements), key=len, reverse=True):
        if re.match(r'^[\d\s.,;:!?\-()]+$', elem):
            continue
        if elem.lower() in ['год', 'г.', 'г', 'лет', 'дня', 'для', 'или', 'ещё', 'уже']:
            continue
        if not any(elem.lower() in e.lower() and len(elem) < len(e) for e in final):
            final.append(elem)
    
    return final


def group_text_by_articles(text):
    """Группирует текст по статьям"""
    lines = text.split('\n')
    titles = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        if (15 <= len(line) <= 80 and line[0].isupper() 
            and not line.endswith('.') and len(line.split()) >= 2
            and not re.match(r'^(www\.|http|\d)', line)):
            if i + 1 < len(lines) and len(lines[i+1].strip()) > 30:
                titles.append({'title': line, 'line': i})
        if line.isupper() and 10 <= len(line) <= 80:
            titles.append({'title': line, 'line': i})
    
    groups = []
    if not titles:
        words = ' '.join(lines).split()
        block, size = [], 0
        for w in words:
            block.append(w)
            size += len(w) + 1
            if size >= 1000:
                groups.append({'title': '', 'text': ' '.join(block)})
                block, size = [], 0
        if block:
            groups.append({'title': '', 'text': ' '.join(block)})
    else:
        for j, t in enumerate(titles):
            end = titles[j+1]['line'] if j+1 < len(titles) else len(lines)
            text_block = ' '.join(l.strip() for l in lines[t['line']:end] if l.strip())
            if len(text_block) > 30:
                groups.append({'title': t['title'], 'text': text_block})
    
    return groups


def clean_text(text):
    text = re.sub(r'[^\s\wа-яёА-ЯЁa-zA-Z0-9.,!?;:()\-"«»„"№%@#$&*+=/]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    return text.strip()


def create_chunks_from_groups(groups, all_elements):
    aggregated = OrderedDict()
    
    for group in groups:
        title = group['title'] or (group['text'][:80].rsplit(' ', 1)[0] + '...' if len(group['text']) > 80 else group['text'])
        text = clean_text(group['text'])
        group_elements = [e for e in all_elements if e.lower() in text.lower()]
        
        if title in aggregated:
            aggregated[title]['content'] += ' ' + text
            aggregated[title]['elements'] = sorted(list(set(aggregated[title]['elements']) | set(group_elements)))
        else:
            aggregated[title] = {'content': text, 'elements': group_elements}
    
    chunks = []
    for i, (theme, data) in enumerate(aggregated.items(), 1):
        content = clean_text(data['content'])
        if len(content) > 500:
            content = content[:500].rsplit(' ', 1)[0] + '...'
        chunks.append({
            'id': i, 'theme': theme[:80], 'content': content,
            'elements': data['elements'][:30], 'elements_count': len(data['elements'])
        })
    
    return chunks


def process_text_to_chunks(text):
    print(f"Обработка текста ({len(text)} символов)...")
    all_elements = extract_meaningful_phrases(text)
    print(f"  Найдено элементов: {len(all_elements)}")
    groups = group_text_by_articles(text)
    print(f"  Выделено блоков: {len(groups)}")
    chunks = create_chunks_from_groups(groups, all_elements)
    print(f"  Создано чанков: {len(chunks)}")
    return chunks


# =====================================================================
# HTML (компактный)
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
        .chunk{background:#fafafa;border:1px solid #e0e0e0;padding:15px;margin-bottom:10px;border-radius:4px}
        .chunk-theme{color:#333;font-weight:700;margin-bottom:10px}
        .chunk-content{color:#555;line-height:1.5;margin-bottom:10px}
        .chunk-elements{display:flex;flex-wrap:wrap;gap:5px}
        .element-tag{background:#e3f2fd;color:#1976D2;padding:3px 8px;border-radius:12px;font-size:12px}
        .tabs{display:flex;gap:10px;margin-bottom:20px;border-bottom:2px solid #e0e0e0;padding-bottom:10px}
        .tab{padding:10px 20px;cursor:pointer;border-radius:4px 4px 0 0;background:#f0f0f0;border:none}
        .tab.active{background:#4CAF50;color:#fff}
        .tab-content{display:none}.tab-content.active{display:block}
        pre{background:#f4f4f4;padding:15px;border-radius:4px;font-size:12px;max-height:500px;overflow:auto}
    </style>
</head>
<body>
<div class="container">
    <h1>📰 Газетный чанкер</h1>
    <div class="upload-area" id="dropZone">
        <p>📁 Перетащите файлы или кликните</p>
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
            <button class="tab active" onclick="showTab('chunks')">📄 Чанки</button>
            <button class="tab" onclick="showTab('json')">📋 JSON</button>
        </div>
        <div class="tab-content active" id="tabChunks"></div>
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
function addFiles(nf){for(let f of nf){const e=f.name.split('.').pop().toLowerCase();if(['pdf','txt','rtf'].includes(e)&&!selectedFiles.find(x=>x.name===f.name&&x.size===f.size))selectedFiles.push(f)}updateFileList()}
function updateFileList(){const l=document.getElementById('fileList'),b=document.getElementById('processBtn');if(!selectedFiles.length){l.innerHTML='';b.disabled=true;return}l.innerHTML=selectedFiles.map((f,i)=>`<div class="file-item"><span>📄 ${f.name} (${formatSize(f.size)})</span><button class="remove-btn" onclick="removeFile(${i})">✕</button></div>`).join('');b.disabled=false}
function removeFile(i){selectedFiles.splice(i,1);updateFileList()}
function clearFiles(){selectedFiles=[];currentResult=null;updateFileList();document.getElementById('results').style.display='none';document.getElementById('progress').style.display='none'}
function formatSize(b){return b<1024?b+' B':b<1048576?(b/1024).toFixed(1)+' KB':(b/1048576).toFixed(1)+' MB'}
async function processFiles(){
    if(!selectedFiles.length)return;
    const p=document.getElementById('progress'),pt=document.getElementById('progressText'),r=document.getElementById('results');
    p.style.display='block';r.style.display='none';pt.textContent='⏳ Обработка...';
    const fd=new FormData();selectedFiles.forEach(f=>fd.append('files',f));
    try{
        const resp=await fetch('/process',{method:'POST',body:fd}),data=await resp.json();
        if(data.error){pt.textContent='❌ '+data.error;setTimeout(()=>p.style.display='none',3000);return}
        currentResult=data;displayResults(data);pt.textContent='✅ Готово!';setTimeout(()=>p.style.display='none',2000)
    }catch(e){pt.textContent='❌ Ошибка';setTimeout(()=>p.style.display='none',3000)}
}
function displayResults(d){
    document.getElementById('resultsSummary').innerHTML=`<strong>📊 Результаты</strong><br>Файлов: ${d.files_processed}<br>Чанков: ${d.total_chunks}<br>Элементов: ${d.total_elements}`;
    let h='';
    for(const[fn,fd]of Object.entries(d.results||{})){h+='<h3>📄 '+fn+'</h3>';if(fd.chunks)fd.chunks.forEach(c=>{h+=`<div class="chunk"><div class="chunk-theme">#${c.id} ${esc(c.theme)}</div><div class="chunk-content">${esc(c.content)}</div><div class="chunk-elements">${(c.elements||[]).map(e=>`<span class="element-tag">${esc(e)}</span>`).join('')}</div></div>`})}
    document.getElementById('tabChunks').innerHTML=h||'<p>Нет данных</p>';
    document.getElementById('tabJson').innerHTML='<pre>'+esc(JSON.stringify(d,null,2))+'</pre>';
    document.getElementById('results').style.display='block'
}
function showTab(n){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab')[n==='chunks'?0:1].classList.add('active');document.getElementById(n==='chunks'?'tabChunks':'tabJson').classList.add('active')}
function downloadJSON(){if(!currentResult)return;const b=new Blob([JSON.stringify(currentResult,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='chunks.json';a.click()}
function downloadTXT(){if(!currentResult)return;let t='';for(const[fn,fd]of Object.entries(currentResult.results||{})){t+='Файл: '+fn+'\\n'+'='.repeat(50)+'\\n\\n';(fd.chunks||[]).forEach(c=>{t+=`ЧАНК ${c.id}\\nТема: ${c.theme}\\nТекст: ${c.content}\\nЭлементы: ${(c.elements||[]).join(', ')}\\n${'-'.repeat(30)}\\n`})}const b=new Blob([t],{type:'text/plain'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='chunks.txt';a.click()}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
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
                total_chunks = total_elements = 0
                
                for filename, file_content in files_data:
                    temp_path = os.path.join(TEMP_DIR, filename)
                    with open(temp_path, 'wb') as f:
                        f.write(file_content)
                    
                    try:
                        ext = os.path.splitext(filename)[1].lower()
                        if ext == '.pdf':
                            text = extract_text_with_unstructured(temp_path)
                        elif ext in ['.txt', '.rtf']:
                            text = extract_text_txt(temp_path)
                        else:
                            continue
                        
                        if text and len(text.strip()) > 50:
                            chunks = process_text_to_chunks(text)
                            results[filename] = {
                                'chunks': chunks,
                                'total_chunks': len(chunks),
                                'total_elements': sum(c['elements_count'] for c in chunks)
                            }
                            total_chunks += len(chunks)
                            total_elements += sum(c['elements_count'] for c in chunks)
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                
                self.send_json({
                    'files_received': len(files_data),
                    'files_processed': len(results),
                    'total_chunks': total_chunks,
                    'total_elements': total_elements,
                    'results': results
                })
            except Exception as e:
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
    print(f"Сервер запущен: http://0.0.0.0:{port}")
    server = HTTPServer(('0.0.0.0', port), ChunkerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен")
        server.server_close()


if __name__ == '__main__':
    main()