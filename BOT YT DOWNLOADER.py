import os
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, CallbackContext
import yt_dlp

# Load environment variables dari file .env
load_dotenv()

# Ambil token bot dari file .env
TOKEN = os.getenv('BOT_TOKEN')

# Lokasi penyimpanan sementara video
DOWNLOAD_PATH = "/public_html/bot.rianphotography.my.id/video"

# Daftar resolusi video yang didukung
SUPPORTED_RESOLUTIONS = [2160, 1440, 1080, 720, 480]

# Fungsi untuk menampilkan pesan selamat datang saat /start diakses
async def start(update: Update, context: CallbackContext) -> None:
    welcome_message = (
        "🎉 Selamat Datang di Video dan Audio Downloader Bot! 🎉\n\n"
        "Kirimkan link video untuk mulai mengunduh.\n\n"
        "Pilih resolusi video, atau unduh hanya audio dalam format M4A."
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

# Fungsi untuk mengunduh audio saja dan mengirimkannya ke pengguna
async def download_audio_only(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    url = context.user_data.get('video_url')
    title = context.user_data.get('title', 'audio')
    if not url:
        await query.edit_message_text("Error: URL tidak ditemukan.")
        return

    # Kirim pesan awal untuk progres
    progress_message = await query.message.reply_text("📥 Memulai unduhan audio...")

    # Konfigurasi yt_dlp untuk mengunduh audio saja dengan progres
    file_path = f"{DOWNLOAD_PATH}/{title}.m4a"
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]',
        'outtmpl': file_path,
        'progress_hooks': [lambda d: progress_hook(d, context, progress_message)],
    }

    try:
        # Mengunduh audio dengan progres
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Kirim file audio ke pengguna setelah unduhan selesai
        with open(file_path, 'rb') as file:
            await query.message.reply_audio(file)

    except Exception as e:
        await progress_message.edit_text(f'Error: {str(e)}')

# Fungsi untuk menangani link video yang dikirimkan oleh pengguna
async def handle_video_link(update: Update, context: CallbackContext) -> None:
    url = update.message.text.strip()
    context.user_data['video_url'] = url

    # Membuat opsi untuk memilih unduhan video atau audio
    keyboard = [
        [InlineKeyboardButton("Unduh Video", callback_data='video')],
        [InlineKeyboardButton("Unduh Audio", callback_data='audio')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Silakan pilih salah satu opsi di bawah ini:', reply_markup=reply_markup)

# Fungsi untuk menangani pilihan pengguna antara video atau audio
async def handle_menu_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Menampilkan resolusi video atau link audio sesuai pilihan
    if query.data == 'video':
        await display_video_resolutions(update, context)
    elif query.data == 'audio':
        await download_audio_only(update, context)

# Fungsi untuk menampilkan opsi resolusi video yang tersedia untuk diunduh
async def display_video_resolutions(update: Update, context: CallbackContext) -> None:
    url = context.user_data.get('video_url')
    query = update.callback_query

    if not url:
        await query.edit_message_text("Error: URL tidak ditemukan.")
        return

    # Konfigurasi yt_dlp untuk hanya menampilkan format yang tersedia
    ydl_opts = {'listformats': True}

    try:
        # Mengambil informasi format video yang tersedia
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            context.user_data['title'] = info.get('title', 'video')

        # Membuat tombol untuk setiap resolusi yang didukung
        buttons = []
        format_dict = {}
        for fmt in formats:
            resolution = fmt.get('height')
            filesize = fmt.get('filesize', 0)

            if resolution in SUPPORTED_RESOLUTIONS and filesize:
                size_mb = round(filesize / (1024 * 1024), 2)
                label = f"{resolution}p - {size_mb}MB"
                
                # Simpan format ID dalam context user_data
                format_dict[fmt['format_id']] = fmt
                buttons.append([InlineKeyboardButton(label, callback_data=f"video_{fmt['format_id']}")])

        # Menyimpan format dalam konteks pengguna dan menampilkan pilihan
        context.user_data['formats'] = format_dict

        # Menampilkan pesan jika tidak ada resolusi yang cocok
        if not buttons:
            await query.edit_message_text('Maaf, tidak ada resolusi yang tersedia sesuai permintaan.')
            return

        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text('Pilih resolusi video yang tersedia:', reply_markup=reply_markup)

    except Exception as e:
        await query.edit_message_text(f'Error: {str(e)}')

# Fungsi untuk memperbarui progres unduhan
def progress_hook(d, context, progress_message):
    if d['status'] == 'downloading':
        percentage = d.get('_percent_str', '0%')
        speed = d.get('_speed_str', '0 KB/s')
        eta = d.get('eta', 0)
        
        # Jalankan update pesan progres secara asinkron menggunakan asyncio
        asyncio.create_task(
            progress_message.edit_text(
                f"📥 Mengunduh...\nProgres: {percentage}\nKecepatan: {speed}\nEstimasi selesai: {eta} detik"
            )
        )
    elif d['status'] == 'finished':
        asyncio.create_task(
            progress_message.edit_text("✅ Unduhan selesai! Mengirim file...")
        )

# Fungsi untuk mengunduh video dengan progres dan mengirimkannya ke pengguna
async def download_video(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    format_id = query.data.split('_')[-1]
    formats = context.user_data.get('formats')
    url = context.user_data.get('video_url')
    title = context.user_data.get('title', 'video')

    if not formats or not url:
        await query.edit_message_text("Error: URL atau format tidak ditemukan.")
        return

    selected_format = formats.get(format_id)

    if not selected_format:
        await query.edit_message_text("Error: Format tidak valid.")
        return

    # Kirim pesan awal untuk progres
    progress_message = await query.message.reply_text("📥 Memulai unduhan...")

    # Konfigurasi yt_dlp untuk mengunduh video dengan hook progres
    file_path = f"{DOWNLOAD_PATH}/{title}.mp4"
    ydl_opts = {
        'format': f'{format_id}+bestaudio[ext=m4a]/best',
        'merge_output_format': 'mp4',
        'outtmpl': file_path,
        'progress_hooks': [lambda d: progress_hook(d, context, progress_message)],
    }

    try:
        # Mengunduh video dengan progres
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Kirim file video ke pengguna setelah unduhan selesai
        with open(file_path, 'rb') as file:
            await query.message.reply_video(file)

    except Exception as e:
        await progress_message.edit_text(f'Error: {str(e)}')


def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_link))
    application.add_handler(CallbackQueryHandler(handle_menu_selection, pattern='^video$|^audio$'))
    application.add_handler(CallbackQueryHandler(download_video, pattern='^video_.*'))
    application.run_polling()

if __name__ == '__main__':
    main()
