# E-posta ve SMS Entegrasyonu Kurulum Talimatları

## 1. Veritabanı Migration

Student modeline `email` ve `phone_number` alanları eklendi. Migration oluşturmak için:

```bash
python manage.py makemigrations
python manage.py migrate
```

**Not:** Eğer migration hatası alırsanız, önce mevcut migration'ları kontrol edin.

## 2. Öğrenci E-posta ve Telefon Ekleme

### Yöntem 1: Django Admin Panel
1. Admin panel'e giriş yapın: `http://127.0.0.1:8000/admin/`
2. Core > Students bölümüne gidin
3. Her öğrenci için email ve phone_number ekleyin

### Yöntem 2: JSON Dosyasından
`static/json/students.json` dosyasına email ve phone_number ekleyin:

```json
{
  "username": "pinar.cetin",
  "email": "pinar.cetin@university.edu",
  "phone_number": "+905551234567",
  ...
}
```

Sonra bir script ile veritabanına yükleyin.

### Yöntem 3: Student Profile Sayfası
Öğrenciler kendi profil sayfalarından email ve telefon ekleyebilir (bu özellik eklenebilir).

## 3. E-posta Ayarları (.env dosyası)

`.env` dosyanıza şu satırları ekleyin:

```env
# Email Configuration
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@university.edu

# Enable/Disable notifications
ENABLE_EMAIL_NOTIFICATIONS=True
ENABLE_SMS_NOTIFICATIONS=True
```

**Gmail için App Password:**
1. Google Account > Security > 2-Step Verification (açık olmalı)
2. App passwords oluşturun
3. Oluşturulan şifreyi `EMAIL_HOST_PASSWORD` olarak kullanın

## 4. SMS Ayarları (Twilio)

### Twilio Hesabı Oluşturma:
1. https://www.twilio.com/ adresine gidin
2. Ücretsiz hesap oluşturun
3. Console'dan Account SID ve Auth Token alın
4. Bir telefon numarası satın alın (trial hesapta ücretsiz numara verilir)

### .env dosyasına ekleyin:
```env
# SMS Configuration (Twilio)
SMS_BACKEND=twilio
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
```

### Twilio Kütüphanesi Kurulumu:
```bash
pip install twilio
```

## 5. Türkiye için SMS Servisi (NetGSM - Opsiyonel)

Eğer Türkiye'de bir SMS servisi kullanmak isterseniz, `core/services/sms_service.py` dosyasındaki `_send_netgsm_sms` fonksiyonunu implement edebilirsiniz.

## 6. Test Etme

### E-posta Testi:
1. Bir öğrenciye email ekleyin
2. Instructor veya Faculty Head olarak bir announcement gönderin
3. Öğrencinin email'ini kontrol edin

### SMS Testi:
1. Bir öğrenciye phone_number ekleyin (format: +905551234567)
2. Instructor veya Faculty Head olarak bir announcement gönderin
3. Öğrencinin telefonuna SMS gelip gelmediğini kontrol edin

## 7. Önemli Notlar

- **Email:** Tüm announcement ve assignment'lar için gönderilir
- **SMS:** Sadece Instructor veya Faculty Head gönderdiğinde gönderilir
- **Phone Number Format:** Uluslararası format kullanın (+90...)
- **Email/SMS Gönderme:** Settings'te `ENABLE_EMAIL_NOTIFICATIONS` ve `ENABLE_SMS_NOTIFICATIONS` ile açıp kapatabilirsiniz

## 8. Sorun Giderme

### Email gönderilmiyor:
- `.env` dosyasındaki email ayarlarını kontrol edin
- Gmail kullanıyorsanız App Password kullandığınızdan emin olun
- Console'da hata mesajlarını kontrol edin

### SMS gönderilmiyor:
- Twilio credentials'ları kontrol edin
- Phone number formatını kontrol edin (+ ile başlamalı)
- Twilio console'da mesajları kontrol edin
- `pip install twilio` yaptığınızdan emin olun

