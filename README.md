# 📰 Газетный чанкер (Newspaper Chunker)

Веб-интерфейс для разбиения газетных публикаций на смысловые чанки с извлечением ключевых элементов (дат, имён, организаций, событий, цитат).

> 🔗 Репозиторий: [https://github.com/MatNM41/newspaper-chunker](https://github.com/MatNM41/newspaper-chunker)

---

## ✨ Возможности

- 📁 **Drag & Drop** загрузка файлов через браузер
- 📄 Поддержка форматов: **PDF, TXT, RTF**
- 🔍 Извлечение **10 категорий** ключевых элементов:
  - Даты и временные периоды
  - Имена людей
  - Организации и бренды
  - Географические названия
  - Культурные объекты
  - Быт и реалии эпохи
  - Цитаты и крылатые фразы
  - Лозунги и идеологемы
  - Числовые показатели
  - Ключевые темы и события
- 📊 Разбиение на смысловые чанки (20-500 символов)
- 📑 Группировка по статьям и темам
- 💾 Автоматическое сохранение в **JSON** и **TXT**
- 🌐 Доступ с любого устройства в локальной сети

---

## 📋 Требования

- **Docker** и **Docker Compose**
- **Git** (для клонирования репозитория)
- 4 ГБ свободной оперативной памяти
- 10 ГБ свободного места на диске
- Порт **5000** должен быть свободен

---

## 🚀 Быстрый старт

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/MatNM41/newspaper-chunker.git
cd newspaper-chunker
docker-compose -p newspaper-chunker up -d

//http://localhost:5000

# Проверить работу
docker ps

# Посмотреть логи
docker-compose -p newspaper-chunker logs -f

# Перезапустить
docker-compose -p newspaper-chunker restart

# Остановить
docker-compose -p newspaper-chunker down

# Запустить снова
docker-compose -p newspaper-chunker up -d

newspaper-chunker/
├── web_chunker.py          # Сервер и чанкер
├── docker-compose.yml      # Docker конфигурация
├── .env                    # Имя проекта
├── .gitignore
├── README.md
├── raw/                    # Папка для газет (авто)
└── Documents/              # Результаты (авто)

