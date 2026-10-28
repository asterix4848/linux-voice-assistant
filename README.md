# Sesli Asistan — Linux

Linux Mint için Matrix tarzı yeşil kod animasyonlu çok dilli sesli asistan. Faster Whisper konuşulan dili otomatik algılar; yerel Qwen3 modeli yanıtı aynı dilde üretmeye çalışır. Ses kaydı, konuşma tanıma, sohbet modeli ve seslendirme bilgisayarda yerel çalışır.

## Şu anki işlevler

- Uygulama açılınca sürekli dinlemeye başlama; mikrofonu 5 saniyelik bölümlerle kullanma.
- Faster Whisper'ın desteklediği dillerde otomatik konuşma tanıma; kullanıcı arayüzü şu an Türkçedir.
- Sohbet yanıtlarını algılanan konuşma dilinde verme (Qwen3 modelinin dil başarımı değişebilir).
- Algılanan dil için Piper kataloğunda bir ses varsa onu kullanma; Piper sesi yoksa `espeak-ng` sesini deneme.
- Küçük, daire biçimli ve masaüstünde taşınabilir asistan penceresi.
- Daire içinde duyulan metin, dinleme halkası ve dinleme/düşünme/cevap sayaçları.
- Kayıt sırasında kalan saniyeyi yüzdelik halka ile gösterme.
- Dinleme, düşünme ve cevap verme sürelerini ayrı ayrı gösteren sayaç.
- Linux'un varsayılan ses girişinden (PipeWire) kayıt alma; Bluetooth mikrofonu Linux ayarlarından seçilir.
- Tanınan metni ekranda gösterip düzeltme.
- Tanınan metni algılanan dilin sesiyle okuma; ayrıca tekrar düğmesi.
- “Bilgisayar”, “computer”, “assistant” ve bazı dillerdeki eşdeğer seslenmelerle yerel sohbet başlatma.
- **Eylemi çalıştır** düğmesine basınca şu dosya/hesap makinesi eylemlerini yürütme:
  - “Ev klasörünü aç”
  - “İndirilenleri aç”
  - “Hesap makinesini aç”
- Kurulu uygulamaları adını söyleyerek açma (sürekli dinlemede sesli onay ister).
- Diğer metinleri komut olarak çalıştırmama.

Bu prototip serbestçe herhangi bir programı/komutu çalıştıran bir ajan değildir ve masaüstünü fareyle kullanmaz.

## Kurulum

### Yerel sohbet modelini kurma

Önce resmi Ollama kurulumunu yap ve Qwen3 sohbet modelini indir:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:1.7b
```

Qwen3 1.7B model dosyası yaklaşık 1,4 GB'tır. Model ve sohbet istekleri bilgisayarda yerel çalışır.

### Masaüstüne kurulum

Proje klasöründeki `install.sh` dosyasını çalıştır. Terminalden:

```bash
bash install.sh
```

Kurulum, uygulamayı kullanıcı hesabının altına kopyalar, Python paketlerini kurar ve masaüstüne ve uygulama menüsüne bir başlatıcı ekler. Yönetici parolası gerekmez. Kurulum tamamlandıktan sonra masaüstü simgesi sağ üstte yaklaşık 8 cm çapında daire biçimli, taşınabilir bir pencere açar; **Büyüt** düğmesi tam arayüzü gösterir. Pencere açıldıktan kısa süre sonra mikrofon dinlemeye başlar. Kapatmak için küçük penceredeki **Çıkış** düğmesini kullan. Kaldırmak için proje klasöründen `bash uninstall.sh` çalıştır.

### Geliştirici kurulumu

Linux Mint'te önce kulaklığı Bluetooth ile bağla. **Ses ayarları → Giriş** bölümünde kulaklığın mikrofonunu seçip seviye göstergesini kontrol et.

Terminalde proje klasörüne geçtikten sonra:

```bash
sudo apt install python3-tk python3-venv pipewire-bin espeak-ng
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

İlk çalıştırmada konuşma tanıma modeli için internet bağlantısı gerekir. Piper, konuşulan dildeki sesi ilk ihtiyaç olduğunda indirir; Piper kataloğunda o dil için ses yoksa sistemde kurulu `espeak-ng` sesi kullanılır. Sesler yerel çalışır. eSpeak sesleri daha robotik duyulabilir ve Whisper'ın tanıdığı her dil için Piper veya eSpeak sesi bulunmayabilir. PyAV sürümü faster-whisper ile uyumlu kalması için 19'dan eski sürümle sınırlandırılır. Uygulamayı kullanırken Codex CLI gerekmez.

## Kullanım

1. Linux Ses ayarlarından Bluetooth kulaklık mikrofonunu varsayılan giriş olarak seç.
2. “Konuş ve yazıya çevir” düğmesine basıp komutu söyle.
3. Tanınan metni kontrol et veya düzelt. Komut adları tanıma modeline ipucu olarak verilir.
4. “Metni sesli tekrar et” düğmesiyle tanınan cümleyi algılanan dilde dinle.
5. Yalnızca yukarıdaki üç komuttan biriyse “Eylemi çalıştır” düğmesine bas.

## Sonraki geliştirme adımları

- Bas-konuş kısayolu ve seçilebilir kayıt süresi.
- Daha fazla güvenli, kullanıcı tarafından seçilebilir eylem.
- İsteğe bağlı yapay zekâ bağlantısı. Bulut modeli kullanılırsa ayrı API erişimi/ücreti gerekebilir ve gönderilen içerik sağlayıcıya iletilir.

## Katkıda bulunma

Fikir, hata bildirimi ve kod katkıları memnuniyetle karşılanır. Önce bir GitHub Issue açarak öneriyi veya sorunu anlat; kod değişikliklerini ayrı bir dalda hazırla ve Pull Request gönder. Katkıların MIT lisansı altında yayımlanacağını unutma.

## Sürekli dinleme modu

Uygulama açıldığında konuşma modeli hazırlanır ve asistan hazır olduğunu sesli söyler. Ardından mikrofonu 5 saniyelik bölümlerle dinler. Sohbet başlatmak için “Bilgisayar”, “computer” veya “assistant” gibi bir seslenmeyle başla; ör. “Hello computer, how are you?” Konuşma dili otomatik algılanır. Ev klasörünü, İndirilenleri ve hesap makinesini açma eylemleri şu an Türkçe ve İngilizce komutlarla tanınır. Asistan komutu tekrarlar ve uygun dilde “evet/yes” onayı gelmeden eylemi yapmaz; “hayır/no” komutu iptal eder. “Dur”, “stop” veya “stop listening” dinleme döngüsünü kapatır.

Sürekli mod yalnızca uygulama açıkken aktiftir. Her kayıt bölümü geçici dosyada tutulur ve tanıma bitince silinir. Dosya açma, kurulu uygulama başlatma ve diğer eylemler dışındaki istekler bilgisayar komutu olarak yürütülmez. Bu mod sık sık yerel konuşma tanıma yaptığı için bilgisayarın işlemcisini meşgul edebilir.
