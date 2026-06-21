import os
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

# Конфигурация
RAW_DIR = r"D:\ПП\ИРЗ\raw"
OUTPUT_DIR = r"D:\ПП\ИРЗ\Documents"
SUPPORTED_EXTENSIONS = {'.doc', '.docx', '.pdf', '.txt', '.rtf', '.odt'}

def extract_text_pdf_docker(input_path):
    """Извлекает текст из PDF через Docker с pdftotext"""
    input_abs = os.path.abspath(input_path)
    input_dir = os.path.dirname(input_abs)
    filename = os.path.basename(input_abs)
    
    check_cmd = ["docker", "images", "-q", "pdf-extractor"]
    result = subprocess.run(check_cmd, capture_output=True, text=True, encoding='utf-8')
    
    if not result.stdout.strip():
        print("Создание образа pdf-extractor...")
        import tempfile
        
        dockerfile = """FROM alpine:latest
RUN apk add --no-cache poppler-utils
ENTRYPOINT ["pdftotext"]
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.Dockerfile', delete=False) as f:
            f.write(dockerfile)
            dockerfile_path = f.name
        
        try:
            build_cmd = [
                "docker", "build", "-t", "pdf-extractor", 
                "-f", dockerfile_path, 
                os.path.dirname(dockerfile_path)
            ]
            subprocess.run(build_cmd, capture_output=True, text=True)
        finally:
            os.unlink(dockerfile_path)
    
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{input_dir}:/data",
        "pdf-extractor",
        "-layout",
        "/data/" + filename,
        "-"
    ]
    
    try:
        print(f"Извлечение текста из PDF...")
        result = subprocess.run(cmd, capture_output=True, timeout=180)
        
        if result.returncode == 0:
            text = None
            for encoding in ['utf-8', 'cp1251', 'cp866', 'koi8-r']:
                try:
                    text = result.stdout.decode(encoding)
                    if text and len(text) > 100:
                        break
                except:
                    continue
            
            if text and text.strip():
                print(f"✓ Извлечено {len(text)} символов")
                return text
            else:
                return None
        else:
            return None
            
    except subprocess.TimeoutExpired:
        print("✗ Таймаут")
        return None
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        return None

def extract_meaningful_phrases(text):
    """Извлекает значимые фразы, имена, события, цитаты (с усиленным поиском дат)"""
    elements = set()
    
    # ==========================================
    # 1. ДАТЫ И ВРЕМЕННЫЕ ПЕРИОДЫ (Максимальный охват)
    # ==========================================
    date_patterns = [
        # Классические: 22 декабря 2022 года, 1 января 2023 г.
        r'\d{1,2}\s+(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])\s+\d{4}\s*(?:год[а]?|г\.)?',
        
        # Цифровые: 22.12.2022, 22.12.22, 22/12/2022, 22-12-2022
        r'\b\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2})\b',
        
        # Год в скобках или с пометкой: (2022), 2022 г., 2022 год
        r'(?:\()?\d{4}(?:\))?\s*(?:год[а]?|г\.|гг\.)?',
        
        # Годы с тире: 2022-2023, 2022–2023, 2022 - 2023
        r'\d{4}\s*[–\-]\s*\d{4}',
        
        # Годы с сокращением: 90-е, 90-е годы, 1990-е
        r'\b\d{2,4}\s*[-–]\s*[ея]+\s*(?:год[аы]?)?',
        
        # Десятилетия и века: XX век, 20 век, 20-й век
        r'(?:XX|XIX|XVIII|XXI)?\s*\d{1,2}[-й]*\s*(?:век[а]?|столети[ея])',
        
        # Месяц и год: декабрь 2022, декабрь 2022 года
        r'(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])\s+\d{4}\s*(?:год[а]?|г\.)?',
        
        # Относительные даты: в прошлом году, в текущем году
        r'(?:прошл[а-яё]+|текущ[а-яё]+|эт[а-яё]+|следующ[а-яё]+)\s+(?:год[ауе]?|месяц[ае]?|недел[яиюе])',
        
        # Время суток и дни: утро, вечер, понедельник
        r'(?:понедельник|вторник|сред[ауе]|четверг|пятниц[ауе]|суббот[ауе]|воскресень[яею])',
        r'(?:утр[ао]|вечер[а]?|ноч[ьи]|день|полдень|полночь)',
        
        # Периоды: с 24 по 28 декабря
        r'с\s+\d{1,2}\s+по\s+\d{1,2}\s+(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])',
        
        # Кварталы: I квартал, первый квартал
        r'(?:I|II|III|IV|перв[а-яё]+|втор[а-яё]+|трет[а-яё]+|четв[ёе]рт[а-яё]+)\s+квартал[а]?',
        
        # Полугодия: первое полугодие, второе полугодие
        r'(?:перв[а-яё]+|втор[а-яё]+)\s+полугоди[ея]',
        
        # Праздники с датами: Новый год, 9 мая, 23 февраля
        r'(?:Новый\s+год|Рождество|Пасх[аи]|Крещение|Маслениц[аы])',
        r'(?:День\s+Побед[аы]|9\s+мая|23\s+февраля|8\s+марта|1\s+мая|4\s+ноября|12\s+июня)',
        
        # Юбилеи и годовщины: 100-летие, 50-летний, 106-й год
        r'\d+[-]?(?:лети[еюя]|летн[яяийего]|годовой|годовщин[аы]|й\s+год)',
        
        # Сезоны: весна 2023, летом 2022
        r'(?:весн[аы]|лет[ао]|осен[ьи]|зим[аы])\s+\d{4}',
        
        # Время с минутами: 12:00, 15-30
        r'\d{1,2}[:.]\d{2}',
        
        # Недели и дни: в течение недели, за 5 дней
        r'(?:в\s+течение|за|на)\s+\d+\s*(?:дн[яейь]|недел[ьяиь]|месяц[ае]в?)',
        
        # Вчера, сегодня, завтра
        r'\b(?:вчера|сегодня|завтра)\b',
    ]
    
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            # Убираем мусорные захваты
            if match.lower() in ['год', 'г.', 'г', 'лет', 'дня', 'для', 'или', 'ещё', 'уже', 'это', 'как', 'что', 'весна', 'лето', 'осень', 'зима']:
                continue
            # Чистим от скобок и лишних пробелов
            match = re.sub(r'[()]', '', match)
            match = re.sub(r'\s+', ' ', match).strip()
            if 3 <= len(match) <= 80:
                elements.add(match)

    # ==========================================
    # 2. ИМЕНА И ФАМИЛИИ
    # ==========================================
    name_patterns = [
        # Стандартные ФИО
        r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?',
        # С должностями: Глава Удмуртии Александр Бречалов, президент Владимир Путин
        r'(?:Глава|Президент|Губернатор|Министр|Депутат|Председатель|Директор|Заместитель)\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?',
    ]
    for pattern in name_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            match = match.strip()
            # Фильтруем ложные срабатывания (длинные цепочки слов)
            if len(match.split()) <= 3 and not re.search(r'(?:Сегодня|Завтра|Вчера|Как|Что|Это|Для|Или|Уже|Ещё)', match):
                elements.add(match)

    # ==========================================
    # 3. ОРГАНИЗАЦИИ И БРЕНДЫ
    # ==========================================
    org_patterns = [
        r'[«"][^«»"]{3,}[»"]',
        r'(?:ООО|ЗАО|ОАО|ПАО|НКО|АО|ИП|ГУП|МУП)\s*[«"][^«»"]+[»"]?',
        r'(?:Правительство|Администрация|Министерство|Госсовет|Госдума|Совет\s+Федерации)\s+(?:России|Удмуртии|РФ|города|района)?',
        r'ГКЧП|СНГ|ООН|НАТО|ЕС|БРИКС|КПСС|ВЛКСМ|СССР',
        r'Беловежск[а-яё]+\s+(?:соглашени[яий]|пуш[ае])',
        r'парад\s+суверенитетов',
    ]
    for pattern in org_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            if len(match) > 3:
                elements.add(match)

    # ==========================================
    # 4. ГЕОГРАФИЯ
    # ==========================================
    geo_patterns = [
        r'г\.\s*[А-ЯЁ][а-яё]+',
        r'ул\.\s*[А-ЯЁ][а-яё]+',
        r'пл\.\s*[А-ЯЁ][а-яё]+',
        r'пр\.\s*[А-ЯЁ][а-яё]+',
        r'Советский\s+Союз|Российская\s+Федераци[яи]|Росси[яи]',
        r'Удмурт(?:и[яи]|ской|ия)|Ижевск[аеу]?|Москв[аые]|Воткинск[ае]?|Сарапул[ае]?|Глазов[ае]?|Можг[ае]?',
        r'БАМ|Ленком|Кремл[ья]|Камчатк[аи]',
        r'Северный\s+Ледовитый|Тихий\s+океан',
    ]
    for pattern in geo_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            if len(match) > 3:
                elements.add(match)

    # ==========================================
    # 5. КУЛЬТУРА И ИСКУССТВО
    # ==========================================
    cultural_patterns = [
        r'Ирония\s+судьбы|Джентльмены\s+удачи|Юнона\s+и\s+Авось',
        r'Союз\s*[-–]\s*Аполлон|олимпийск[а-яё]+\s+Мишка',
        r'Высоцк[а-яё]+|Визбор[а]?|Гагарин[а]?',
        r'(?:фильм|книга|песня|спектакль|опера|балет|картина|памятник|музей|театр|выставка)\s+[«"][^«»"]+[»"]',
    ]
    for pattern in cultural_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            if len(match) > 3:
                elements.add(match)

    # ==========================================
    # 6. БЫТ И РЕАЛИИ
    # ==========================================
    everyday_patterns = [
        r'калачик\s+за\s+\d+\s+копеек|батон\s+за\s+\d+',
        r'талоны\s+на\s+(?:масло|сапоги|водку|мясо|сахар)',
        r'автомат[ы]?\s+с\s+газированн[а-яё]+',
        r'пионерск[а-яё]+\s+(?:кост[а-яё]+|лагер[яь]|галстук)',
        r'железный\s+занавес|холодная\s+война',
        r'дефицит|субботник|воскресник|комсомол[её]ц',
        r'первомайск[а-яё]+\s+демонстраци[яи]',
        r'брежневск[а-яё]+\s+застой',
    ]
    for pattern in everyday_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            if len(match) > 3:
                elements.add(match)

    # ==========================================
    # 7. ЦИТАТЫ И КРЫЛАТЫЕ ФРАЗЫ
    # ==========================================
    quote_patterns = [
        r'где\s+(?:всё|все)\s+(?:просто|ясно)\s+и\s+(?:знакомо|понятно)',
        r'наш\s+адрес\s*[-–]\s*Советский\s+Союз',
        r'солнце\s+(?:ярче|светит)\s+(?:и|а)\s+трава\s+(?:зеленее|зеленей)',
        r'уверены\s+в\s+завтрашнем\s+дне',
        r'вс[ёе]\s+(?:ещё|только)\s+впереди',
        r'мы\s+(?:родом|сами)\s+(?:из|родом\s+из)\s+СССР',
        r'сделано\s+в\s+СССР',
    ]
    for pattern in quote_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            if len(match) > 5:
                elements.add(match)

    # ==========================================
    # 8. ЛОЗУНГИ И ИДЕОЛОГЕМЫ
    # ==========================================
    slogan_patterns = [
        r'Великая\s+Побед[аы]',
        r'един(?:ый|ая|ое)\s+и\s+(?:могучий|нерушимый|великий)',
        r'дружб[аы]\s+народов',
        r'пролетарии\s+всех\s+стран',
        r'мир\s*[-–]\s*труд\s*[-–]\s*май',
        r'слава\s+(?:КПСС|труду|народу)',
        r'впер[ёе]д\s+к\s+(?:победе|коммунизму)',
        r'пятилетк[ау]',
        r'ударник\s+(?:коммунистического\s+)?труда',
    ]
    for pattern in slogan_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            if len(match) > 3:
                elements.add(match)

    # ==========================================
    # 9. ЧИСЛА И ПОКАЗАТЕЛИ
    # ==========================================
    number_patterns = [
        r'\d+[\s]*(?:миллион|миллиард|тысяч|процент|рубл[еяй]|копе[её]к|человек|метр|километр|гектар|тонн|млрд|млн|тыс\.)',
        r'\d+[.,]\d+\s*(?:млн|млрд|тыс\.|%|руб\.)?',
    ]
    for pattern in number_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            if len(match) > 3:
                elements.add(match)

    # ==========================================
    # 10. КЛЮЧЕВЫЕ ТЕМЫ И СОБЫТИЯ
    # ==========================================
    theme_patterns = [
        r'(?:бюджет|финансирование|строительство|ремонт|реконструкци[яи]|'
        r'модернизаци[яи]|оптимизаци[яи]|реформ[аы]|программ[аы]|проект[аы]?|'
        r'выбор[аы]|голосование|референдум|'
        r'образование|здравоохранение|культура|спорт|туризм|'
        r'сельское\s+хозяйство|промышленность|транспорт|энергетика|'
        r'экология|природа|заповедник|пенси[яи]|пособи[ея]|льгот[аы]|'
        r'коронавирус|пандеми[яи]|вакцинаци[яи]|'
        r'СВО|спецопераци[яи]|мобилизаци[яи]|'
        r'юбилей|годовщин[аы]|столетие|открытие|закрытие|'
        r'концерт|фестиваль|ярмарка|выставка|форум|конференци[яи]|'
        r'соревновани[яе]|чемпионат|олимпиад[аы]|спартакиад[аы])',
    ]
    for pattern in theme_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            match = match.strip()
            if len(match) > 3:
                elements.add(match)

    # ==========================================
    # ФИЛЬТРАЦИЯ И ОЧИСТКА
    # ==========================================
    final_elements = []
    elements_list = sorted(list(elements), key=len, reverse=True)
    
    for elem in elements_list:
        # Убираем мусор
        if re.match(r'^[\d\s.,;:!?\-()]+$', elem):
            continue
        if elem.lower() in ['год', 'г.', 'г', 'лет', 'дня', 'для', 'или', 'ещё', 'уже', 'это', 'как', 'что']:
            continue
        
        # Убираем подстроки
        is_substring = False
        for existing in final_elements:
            if elem.lower() in existing.lower() and len(elem) < len(existing):
                is_substring = True
                break
        
        if not is_substring:
            final_elements.append(elem)
    
    return final_elements

def group_text_by_articles(text):
    """Группирует текст по логическим блокам (статьям)"""
    lines = text.split('\n')
    
    # Находим потенциальные заголовки
    titles = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # Признаки заголовка
        is_title = False
        
        # Короткая строка, начинается с большой буквы
        if (15 <= len(line) <= 80 
            and line[0].isupper() 
            and not line.endswith('.')
            and not line.endswith(',')
            and len(line.split()) >= 2
            and not re.match(r'^(www\.|http|https)', line)
            and not re.match(r'^\d+[\s\d.,;]*$', line)):
            
            # Проверяем контекст
            if i + 1 < len(lines) and len(lines[i+1].strip()) > 30:
                is_title = True
        
        # Строка в верхнем регистре
        if line.isupper() and 10 <= len(line) <= 80:
            is_title = True
        
        if is_title:
            titles.append({'title': line, 'line': i})
    
    # Группируем текст между заголовками
    groups = []
    
    if not titles:
        # Если заголовков нет, делим на большие блоки
        full_text = ' '.join(lines)
        # Разбиваем на блоки примерно по 1000 символов
        words = full_text.split()
        block = []
        block_size = 0
        
        for word in words:
            block.append(word)
            block_size += len(word) + 1
            if block_size >= 1000:
                groups.append({
                    'title': '',
                    'text': ' '.join(block)
                })
                block = []
                block_size = 0
        
        if block:
            groups.append({
                'title': '',
                'text': ' '.join(block)
            })
    else:
        # Группируем по заголовкам
        for j, title_info in enumerate(titles):
            start_line = title_info['line']
            
            # Конец - следующий заголовок или конец текста
            if j + 1 < len(titles):
                end_line = titles[j + 1]['line']
            else:
                end_line = len(lines)
            
            # Собираем текст
            block_lines = lines[start_line:end_line]
            block_text = ' '.join(line.strip() for line in block_lines if line.strip())
            
            if len(block_text) > 30:
                groups.append({
                    'title': title_info['title'],
                    'text': block_text
                })
    
    return groups

def create_chunks_from_groups(groups, all_elements):
    """Создает чанки из групп, объединяя по темам"""
    # Словарь для агрегации по темам
    aggregated = OrderedDict()
    
    for group in groups:
        title = group['title']
        text = group['text']
        
        if not title:
            # Если нет заголовка, используем первые 80 символов как тему
            title = text[:80]
            if len(text) > 80:
                title = title.rsplit(' ', 1)[0] + '...'
        
        # Очищаем текст
        text = clean_text(text)
        
        # Находим элементы для этого текста
        group_elements = [e for e in all_elements if e.lower() in text.lower()]
        
        if title in aggregated:
            # Объединяем с существующим
            aggregated[title]['content'] += ' ' + text
            # Объединяем элементы без дубликатов
            existing = set(aggregated[title]['elements'])
            existing.update(group_elements)
            aggregated[title]['elements'] = sorted(list(existing))
        else:
            aggregated[title] = {
                'content': text,
                'elements': group_elements
            }
    
    # Преобразуем в список чанков
    chunks = []
    for i, (theme, data) in enumerate(aggregated.items(), 1):
        # Очищаем объединенный текст
        content = clean_text(data['content'])
        
        # Обрезаем если слишком длинный
        if len(content) > 500:
            content = content[:500]
            # Обрезаем до последнего пробела
            content = content.rsplit(' ', 1)[0] + '...'
        
        chunks.append({
            'id': i,
            'theme': theme[:80],
            'content': content,
            'elements': data['elements'][:30],
            'elements_count': len(data['elements'])
        })
    
    return chunks

def clean_text(text):
    """Очистка текста"""
    text = re.sub(r'[^\s\wа-яёА-ЯЁa-zA-Z0-9.,!?;:()\-"«»„"№%@#$&*+=/]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    return text.strip()

def process_file(file_path):
    """Обработка одного файла"""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        text = extract_text_pdf_docker(file_path)
    elif ext in ['.txt', '.rtf']:
        try:
            with open(file_path, 'rb') as f:
                raw = f.read()
            for enc in ['utf-8', 'cp1251', 'cp866']:
                try:
                    text = raw.decode(enc)
                    break
                except:
                    continue
        except Exception as e:
            print(f"✗ Ошибка чтения: {e}")
            return None
    else:
        print(f"✗ Формат {ext} пока не поддерживается")
        return None
    
    if not text or len(text.strip()) < 50:
        print("✗ Мало текста")
        return None
    
    # Извлекаем все значимые элементы
    all_elements = extract_meaningful_phrases(text)
    print(f"✓ Найдено {len(all_elements)} значимых элементов")
    
    # Группируем текст по логическим блокам
    groups = group_text_by_articles(text)
    print(f"✓ Выделено {len(groups)} тематических блоков")
    
    # Создаем чанки с агрегацией по темам
    chunks = create_chunks_from_groups(groups, all_elements)
    print(f"✓ Создано {len(chunks)} уникальных чанков")
    
    return chunks

def save_results(chunks, original_filename, relative_path):
    """Сохранение результатов"""
    base_name = Path(original_filename).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON
    json_file = os.path.join(OUTPUT_DIR, f"{base_name}_{timestamp}.json")
    json_data = {
        'name': original_filename,
        'path': relative_path,
        'date': datetime.now().isoformat(),
        'chunks_count': len(chunks),
        'total_elements': sum(c['elements_count'] for c in chunks),
        'chunks': chunks
    }
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    # TXT
    txt_file = os.path.join(OUTPUT_DIR, f"{base_name}_{timestamp}.txt")
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(f"Файл: {original_filename}\n")
        f.write(f"Путь: {relative_path}\n")
        f.write(f"Дата обработки: {datetime.now().isoformat()}\n")
        f.write(f"Всего чанков: {len(chunks)}\n")
        f.write(f"Всего элементов: {sum(c['elements_count'] for c in chunks)}\n")
        f.write("="*70 + "\n\n")
        
        for chunk in chunks:
            f.write(f"ЧАНК {chunk['id']}\n")
            f.write(f"Тема: {chunk['theme']}\n")
            f.write(f"Текст: {chunk['content']}\n")
            f.write(f"Элементы ({chunk['elements_count']}): {', '.join(chunk['elements'][:20])}\n")
            f.write("="*70 + "\n\n")
    
    return json_file, txt_file

def find_files(directory):
    """Поиск файлов рекурсивно"""
    files = []
    for root, _, filenames in os.walk(directory):
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTENSIONS:
                files.append(os.path.join(root, fn))
    return files

def main():
    print("=" * 60)
    print("  ГАЗЕТНЫЙ ЧАНКЕР v8.0 - УНИКАЛЬНЫЕ ЧАНКИ")
    print("=" * 60)
    print()
    
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    files = find_files(RAW_DIR)
    
    if not files:
        print(f"Нет файлов в {RAW_DIR}")
        return
    
    print(f"Найдено файлов: {len(files)}\n")
    
    ok = 0
    for i, fp in enumerate(files, 1):
        fn = os.path.basename(fp)
        size_mb = os.path.getsize(fp) / 1024 / 1024
        rel_path = os.path.relpath(fp, RAW_DIR)
        
        print(f"\n{'='*50}")
        print(f"[{i}/{len(files)}] {fn} ({size_mb:.1f} МБ)")
        print(f"Путь: {rel_path}")
        print('='*50)
        
        chunks = process_file(fp)
        
        if chunks:
            jf, tf = save_results(chunks, fn, rel_path)
            print(f"✓ Сохранено:")
            print(f"  JSON: {os.path.basename(jf)}")
            print(f"  TXT:  {os.path.basename(tf)}")
            print(f"  Чанков: {len(chunks)}")
            print(f"  Элементов всего: {sum(c['elements_count'] for c in chunks)}")
            
            # Пример
            if chunks:
                print(f"\nПример чанка:")
                print(f"  Тема: {chunks[0]['theme'][:60]}")
                print(f"  Текст: {chunks[0]['content'][:80]}...")
                print(f"  Элементов: {chunks[0]['elements_count']}")
                if chunks[0]['elements']:
                    print(f"  Элементы: {', '.join(chunks[0]['elements'][:5])}")
            
            ok += 1
        else:
            print(f"✗ Файл не обработан")
    
    print(f"\n{'='*50}")
    print(f"ГОТОВО! Обработано: {ok}/{len(files)}")
    print(f"Результаты: {OUTPUT_DIR}")
    print('='*50)

if __name__ == "__main__":
    main()