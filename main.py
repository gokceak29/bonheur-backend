from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import google.generativeai as genai 
import os 

app = FastAPI()

# --- YAPAY ZEKA AYARLARI ---
# Buradaki tırnak içine kendi API anahtarını yapıştır 
api_anahtari = os.environ.get("GEMINI_API_KEY") 
genai.configure(api_key=api_anahtari) 
yapay_zeka_modeli = genai.GenerativeModel('gemini-2.5-flash')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VERİ ŞABLONLARI ---
class KayitVerisi(BaseModel):
    ad_soyad: str
    email: str
    sifre: str

class GirisVerisi(BaseModel):
    email: str
    sifre: str

class SifreYenileVerisi(BaseModel):
    email: str
    yeni_sifre: str

class ChatVerisi(BaseModel):
    mesaj: str 

# YENİ EKLENEN: Sepetteki her bir ürünü temsil eden şablon
class SepetUrunu(BaseModel):
    urun_id: int
    adet: int

# GÜNCELLENEN: Sipariş artık tutarla birlikte ürünleri de alıyor
class SiparisVerisi(BaseModel):
    email: str
    toplam_tutar: float 
    urunler: list[SepetUrunu] 

# --- MÜŞTERİ KAYIT ---
@app.post("/kayit")
def kayit_ol(veri: KayitVerisi):
    baglanti = sqlite3.connect("kafe.db")
    cursor = baglanti.cursor()
    try:
        isim_parcalari = veri.ad_soyad.strip().split(" ", 1)
        ad = isim_parcalari[0]
        soyad = isim_parcalari[1] if len(isim_parcalari) > 1 else ""
        cursor.execute("INSERT INTO MUSTERI (Ad, Soyad, Email, Sifre) VALUES (?, ?, ?, ?)", (ad, soyad, veri.email, veri.sifre))
        baglanti.commit()
        return {"durum": "ok"}
    except:
        raise HTTPException(status_code=400, detail="Bu e-posta zaten kayıtlı.")
    finally:
        baglanti.close()

# --- MÜŞTERİ GİRİŞİ ---
@app.post("/giris")
def giris_yap(veri: GirisVerisi):
    baglanti = sqlite3.connect("kafe.db")
    cursor = baglanti.cursor()
    cursor.execute("SELECT Sifre, Ad FROM MUSTERI WHERE Email = ?", (veri.email,))
    kullanici = cursor.fetchone()
    baglanti.close()
    if not kullanici:
        raise HTTPException(status_code=400, detail="E-posta bulunamadı.")
    if kullanici[0] != veri.sifre:
        raise HTTPException(status_code=400, detail="Hatalı şifre!")
    return {"ad": kullanici[1]}

# --- ŞİFRE YENİLEME ---
@app.post("/sifre-yenile")
def sifre_yenile(veri: SifreYenileVerisi):
    baglanti = sqlite3.connect("kafe.db")
    cursor = baglanti.cursor()
    cursor.execute("UPDATE MUSTERI SET Sifre = ? WHERE Email = ?", (veri.yeni_sifre, veri.email))
    baglanti.commit()
    baglanti.close()
    return {"mesaj": "Şifreniz güncellendi."}

# --- PERSONEL GİRİŞİ ---
@app.post("/personel-giris")
def personel_giris(veri: GirisVerisi):
    baglanti = sqlite3.connect("kafe.db")
    cursor = baglanti.cursor()
    try:
        cursor.execute("SELECT * FROM PERSONEL WHERE Ad = ? AND Sifre = ?", (veri.email, veri.sifre))
        personel = cursor.fetchone()
        
        if personel: 
            return {"mesaj": f"Sisteme başarıyla giriş yapıldı. İyi mesailer, {personel[1]}!"}
        else: 
            raise HTTPException(status_code=400, detail="Personel adı veya şifresi hatalı.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail="Veritabanı hatası: " + str(e))
    finally:
        baglanti.close() 

# --- MENÜYÜ GETİR ---
@app.get("/menu")
def menuyu_getir():
    baglanti = sqlite3.connect("kafe.db")
    cursor = baglanti.cursor()
    sorgu = "SELECT M.UrunID, K.Ad, M.Ad, M.Fiyat, M.Resim_URL FROM MENU_URUNU M JOIN KATEGORI K ON M.KategoriID = K.KategoriID WHERE M.Aktif_Mi = 1"
    cursor.execute(sorgu)
    satirlar = cursor.fetchall()
    baglanti.close()
    return [{"id":s[0], "kategori":s[1], "ad":s[2], "fiyat":s[3], "resim_url":s[4]} for s in satirlar]

# --- YAPAY ZEKA CHATBOT ---
gecmis_hafiza = []
@app.post("/chatbot")
def chatbot_cevapla(veri: ChatVerisi):
    global gecmis_hafiza 
    try:
        baglanti = sqlite3.connect("kafe.db")
        imlec = baglanti.cursor()
        
        imlec.execute("SELECT Ad, Fiyat FROM Menu_Urunu") 
        urunler = imlec.fetchall()
        baglanti.close()

        guncel_menu_metni = "Kafemizin Güncel Menüsü ve Fiyatları:\n"
        for urun in urunler:
            guncel_menu_metni += f"- {urun[0]}: {urun[1]} TL\n"

        sistem_talimati = f"""
        Sen 'Bonheur Cafe' adında çok şık bir kafenin dijital asistanısın.
        Aşağıda sana anlık olarak veritabanımızdan çekilen güncel menümüzü ve fiyatlarımızı veriyorum:
        
        {guncel_menu_metni}

        KURALLAR:
        1. Menü ve Fiyatlar: Müşteriye SADECE yukarıdaki listede bulunan ürünleri önerebilirsin.
        2. Olmayan Ürünler: Müşteri listede olmayan bir ürün isterse, bizde bulunmadığını söyle ve alternatif öner.
        3. Kısa ve Öz Ol: Cevaplarını kısa, net ve sohbet havasında tut.
        4. İşaret Kullanma: Cevaplarında yıldız işareti veya vurgu formatları KULLANMA.
        5. İnteraktif Bilgi: Müşteri bir ürün sorduğunda kısaca anlat. Ürün hakkında kalori bilgisi isterse kendi genel kültürünü kullanarak mantıklı bir ortalama kalorisi bilgisi ver. Doğrudan alerjen/vegan sorulmadıysa sonuna ekle: "Dilerseniz alerjen durumu ve vegan uygunluğu hakkında da bilgi verebilirim?"
        6. Onay ve Hafıza Durumu: Müşteri "evet", "olur", "tiramisu", "isterim" gibi bir önceki sohbeti devam ettiren kelimeler kullanırsa, konuşma geçmişini hatırla ve bahsi geçen ürünün alerjen/vegan bilgilerini detaylıca açıkla. Fiyatı tekrar söyleme.
        7. Üslup: Asla kalın punto kullanma. Çok nazik ve şık bir kafe asistanı ol. 🥐
        """
        
        yapay_zeka_modeli = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction=sistem_talimati
        )
        
        sohbet = yapay_zeka_modeli.start_chat(history=gecmis_hafiza)
        cevap = sohbet.send_message(veri.mesaj)
        
        gecmis_hafiza = list(sohbet.history)
        
        if len(gecmis_hafiza) > 10:
            gecmis_hafiza = gecmis_hafiza[-10:]
            
        return {"cevap": cevap.text}

    except Exception as e:
        print("\n" + "!"*50)
        print("🚨 YAPAY ZEKA HATASI DETAYI:")
        print(str(e))
        print("!"*50 + "\n")
        return {"cevap": "Şu anda şeflerimizle iletişim kuramıyorum, lütfen birazdan tekrar dener misiniz? 🥐"} 
    
# --- SİPARİŞ TAMAMLAMA VE DETAY KAYDI (GÜNCELLENDİ) ---
@app.post("/siparisi-tamamla")
def siparisi_tamamla(veri: SiparisVerisi):
    baglanti = sqlite3.connect("kafe.db")
    cursor = baglanti.cursor()
    
    try:
        cursor.execute("SELECT MusteriID FROM MUSTERI WHERE Email = ?", (veri.email,))
        musteri = cursor.fetchone()
        
        if not musteri:
            raise HTTPException(status_code=404, detail="Sipariş için giriş yapmanız gerekiyor.")
            
        musteri_id = musteri[0]
        kazanilan_puan = int(veri.toplam_tutar) 
        
        cursor.execute("UPDATE SADAKAT_CUZDANI SET Toplam_Puan = Toplam_Puan + ? WHERE MusteriID = ?", 
                       (kazanilan_puan, musteri_id)) 
        
        # 1. Ana siparişi kaydet
        cursor.execute("INSERT INTO SIPARIS (MusteriID, Toplam_Tutar, Durum) VALUES (?, ?, ?)", 
                       (musteri_id, veri.toplam_tutar, 'Hazırlanıyor')) 
        
        yeni_siparis_id = cursor.lastrowid
        
        # 2. Sepetteki ürünleri detay tablosuna kaydet
        for urun in veri.urunler:
            cursor.execute("INSERT INTO SIPARIS_DETAY (SiparisID, UrunID, Adet) VALUES (?, ?, ?)", 
                           (yeni_siparis_id, urun.urun_id, urun.adet))
        
        baglanti.commit()
        return {"mesaj": f"Siparişiniz hazırlanıyor! Bu siparişten {kazanilan_puan} Bonheur Puanı kazandınız. 🎉"}
        
    except Exception as e:
        baglanti.rollback()
        raise HTTPException(status_code=500, detail="Sipariş işlenirken bir hata oluştu: " + str(e))
    finally:
        baglanti.close() 

# --- MUTFAK: BEKLEYEN SİPARİŞLERİ LİSTELE (GÜNCELLENDİ) ---
@app.get("/bekleyen-siparisler")
def bekleyen_siparisler():
    baglanti = sqlite3.connect("kafe.db")
    baglanti.row_factory = sqlite3.Row 
    cursor = baglanti.cursor()
    
    # Bekleyen siparişleri çekiyoruz
    sorgu = """
        SELECT S.SiparisID, M.Ad, S.Toplam_Tutar, S.Tarih 
        FROM SIPARIS S 
        JOIN MUSTERI M ON S.MusteriID = M.MusteriID 
        WHERE S.Durum = 'Hazırlanıyor'
        ORDER BY S.Tarih DESC
    """
    cursor.execute(sorgu)
    ana_siparisler = cursor.fetchall()
    
    sonuclar = []
    
    # Her siparişin içindeki ürünleri çekip listeye ekliyoruz
    for siparis in ana_siparisler:
        siparis_dict = dict(siparis)
        
        cursor.execute("""
            SELECT MU.Ad, SD.Adet  
            FROM SIPARIS_DETAY SD
            JOIN MENU_URUNU MU ON SD.UrunID = MU.UrunID
            WHERE SD.SiparisID = ?
        """, (siparis_dict['SiparisID'],))
        urunler = cursor.fetchall()
        
        sonuclar.append({
            "id": siparis_dict['SiparisID'],
            "musteri": siparis_dict['Ad'],
            "tutar": siparis_dict['Toplam_Tutar'],
            "tarih": siparis_dict['Tarih'],
            "urunler": [{"ad": u["Ad"], "adet": u["Adet"]} for u in urunler] 
        })

    baglanti.close()
    return sonuclar

# --- MÜŞTERİ PROFİLİ VE PUAN SORGULAMA ---
@app.get("/profil/{email}")
def profil_getir(email: str):
    baglanti = sqlite3.connect("kafe.db")
    cursor = baglanti.cursor()
    try:
        # Müşteri bilgileri ile sadakat cüzdanını birleştirip (JOIN) çekiyoruz
        sorgu = """
            SELECT M.Ad, M.Soyad, M.Email, S.Toplam_Puan 
            FROM MUSTERI M
            LEFT JOIN SADAKAT_CUZDANI S ON M.MusteriID = S.MusteriID
            WHERE M.Email = ?
        """
        cursor.execute(sorgu, (email,))
        profil = cursor.fetchone()
        
        if not profil:
            raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
            
        # Eğer müşterinin henüz cüzdanı oluşmamışsa (NULL ise) puanı 0 gösteriyoruz
        puan = profil[3] if profil[3] is not None else 0
        
        return {
            "ad": profil[0],
            "soyad": profil[1],
            "email": profil[2],
            "puan": puan
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        baglanti.close()

# --- MUTFAK: SİPARİŞİ TAMAMLANDI OLARAK İŞARETLE ---
@app.post("/siparis-onayla/{siparis_id}")
def siparis_onayla(siparis_id: int):
    baglanti = sqlite3.connect("kafe.db")
    cursor = baglanti.cursor()
    cursor.execute("UPDATE SIPARIS SET Durum = 'Tamamlandı' WHERE SiparisID = ?", (siparis_id,))
    baglanti.commit()
    baglanti.close()
    return {"mesaj": "Sipariş teslim edildi!"}