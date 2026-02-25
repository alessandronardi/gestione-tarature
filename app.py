import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pyairtable import Api

# Configurazione pagina
st.set_page_config(page_title="Registro Tarature", page_icon="📏", layout="wide")

# Connessione sicura ad Airtable tramite i Secrets di Streamlit
# Questi valori li imposteremo nella dashboard di Streamlit Cloud
api = Api(st.secrets["AIRTABLE_PAT"])
base_id = st.secrets["AIRTABLE_BASE_ID"]

# Colleghiamo le due tabelle
tabella_registro = api.table(base_id, "Registro")
tabella_storico = api.table(base_id, "Storico")

# --- FUNZIONI DI LETTURA E SALVATAGGIO CON AIRTABLE ---
def carica_registro():
    records = tabella_registro.all()
    # Estraiamo i campi da Airtable e aggiungiamo l'ID di sistema del record
    dati = [{"id_airtable": r["id"], **r["fields"]} for r in records]
    df = pd.DataFrame(dati)
    
    if not df.empty:
        # Assicuriamoci che tutte le colonne esistano anche se Airtable non invia i campi vuoti
        colonne_attese = ["id_airtable", "Matricola", "Strumento", "Modello", "Seriale costruttore", "Data Taratura", "Data Scadenza"]
        for col in colonne_attese:
            if col not in df.columns:
                df[col] = ""
                
        df['Matricola'] = df['Matricola'].astype(str)
# errors='coerce' trasforma automaticamente gli errori o le celle vuote in 'NaT' in modo sicuro
        df['Data Taratura'] = pd.to_datetime(df['Data Taratura'], errors='coerce')
        df['Data Scadenza'] = pd.to_datetime(df['Data Scadenza'], errors='coerce')
    return df

def carica_storico():
    records = tabella_storico.all()
    dati = [r["fields"] for r in records]
    return pd.DataFrame(dati)

# --- INTERFACCIA UTENTE ---
st.title("📏 Gestione Strumenti e Tarature")

df_registro = carica_registro()
oggi = pd.Timestamp("today").normalize()
soglia_avviso = oggi + pd.Timedelta(days=30)

# 1. SEZIONE AVVISI
if not df_registro.empty:
    scaduti = df_registro[df_registro['Data Scadenza'] < oggi]
    in_scadenza = df_registro[(df_registro['Data Scadenza'] >= oggi) & (df_registro['Data Scadenza'] <= soglia_avviso)]
    
    if not scaduti.empty:
        st.error(f"⚠️ ATTENZIONE: Ci sono {len(scaduti)} strumenti con taratura SCADUTA!")
    if not in_scadenza.empty:
        st.warning(f"🔔 AVVISO: {len(in_scadenza)} strumenti scadranno nei prossimi 30 giorni.")

st.divider()

# 2. INSERIMENTO O AGGIORNAMENTO STRUMENTO
st.subheader("➕ Aggiungi o Aggiorna Taratura")
st.write("Inserisci una nuova matricola per creare uno strumento, o una esistente per aggiornare la sua taratura.")

with st.form("form_inserimento", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        matricola = st.text_input("Matricola / ID Interno")
        nome = st.text_input("Nome Strumento")
    with col2:
        modello = st.text_input("Marca e Modello")
        seriale = st.text_input("Seriale costruttore")
    with col3:
        data_tar = st.date_input("Data di esecuzione taratura", value=oggi)
        data_scad = st.date_input("Data di scadenza", value=oggi + timedelta(days=365))
        
    inviato = st.form_submit_button("Salva Taratura")
    
    if inviato and matricola and nome:
        # Prepara i dati nel formato richiesto da Airtable
        dati_record = {
            "Matricola": str(matricola),
            "Strumento": nome,
            "Modello": modello,
            "Seriale costruttore": seriale,
            "Data Taratura": data_tar.strftime("%Y-%m-%d"),
            "Data Scadenza": data_scad.strftime("%Y-%m-%d")
        }
        
        # 1. AGGIORNO O CREO NEL REGISTRO
        if not df_registro.empty and matricola in df_registro['Matricola'].values:
            # Trova l'ID di sistema Airtable per quella matricola e aggiorna
            id_da_aggiornare = df_registro[df_registro['Matricola'] == matricola].iloc[0]['id_airtable']
            tabella_registro.update(id_da_aggiornare, dati_record)
            st.success(f"Taratura aggiornata per lo strumento: {matricola}")
        else:
            # Crea un nuovo record
            tabella_registro.create(dati_record)
            st.success(f"Nuovo strumento inserito: {matricola}")
            
        # 2. LOG NEL FOGLIO STORICO
        tabella_storico.create({
            "Data Registrazione": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Matricola": str(matricola),
            "Strumento": nome,
            "Data Taratura": data_tar.strftime("%Y-%m-%d"),
            "Data Scadenza": data_scad.strftime("%Y-%m-%d")
        })
        
        st.rerun()

st.divider()

# 3. VISUALIZZAZIONE REGISTRO (Nascondiamo l'ID di sistema all'utente)
st.subheader("📋 Registro Attuale")
if not df_registro.empty:
    df_vista = df_registro.drop(columns=["id_airtable"], errors='ignore')
    
    def evidenzia_scadenze(riga):
        if riga['Data Scadenza'] < oggi:
            return ['background-color: #ffcccc; color: black'] * len(riga)
        elif riga['Data Scadenza'] <= soglia_avviso:
            return ['background-color: #fff0b3; color: black'] * len(riga)
        else:
            return [''] * len(riga)
            
    st.dataframe(df_vista.style.apply(evidenzia_scadenze, axis=1), use_container_width=True, hide_index=True)
else:
    st.info("Il registro è vuoto.")

st.divider()

# 4. CREAZIONE RAPPORTO E STORICO
colA, colB = st.columns([1, 1])

with colA:
    st.subheader("📄 Genera Rapporto di Taratura")
    if not df_registro.empty:
        lista_strumenti = df_registro['Strumento'] + " (Matr: " + df_registro['Matricola'] + ")"
        scelta = st.selectbox("Seleziona lo strumento:", lista_strumenti)
        
        matr_selezionata = scelta.split("(Matr: ")[1].replace(")", "")
        dati_strumento = df_registro[df_registro['Matricola'] == matr_selezionata].iloc[0]
        stato = "SCADUTO" if dati_strumento['Data Scadenza'] < oggi else "IN CORSO DI VALIDITÀ"
        
        testo_rapporto = f"""========================================
CERTIFICATO INTERNO DI TARATURA E CONTROLLO
========================================

INFORMAZIONI STRUMENTO:
- Nome Strumento: {dati_strumento['Strumento']}
- Marca/Modello: {dati_strumento['Modello']}
- Seriale Costruttore: {dati_strumento.get('Seriale costruttore', 'N/D')}
- Numero di Matricola Interna: {dati_strumento['Matricola']}

DETTAGLI TARATURA:
- Data di esecuzione taratura: {str_tar}
- Data di prossima scadenza: {str_scad}
- Stato attuale dello strumento: {stato}

Il presente documento attesta che lo strumento è inserito a registro.
----------------------------------------
Data di generazione: {oggi.strftime("%d/%m/%Y")}
Firma del Responsabile: _______________________
"""
        st.download_button(
            label="⬇️ Scarica Rapporto (.txt)",
            data=testo_rapporto,
            file_name=f"Rapporto_Taratura_{dati_strumento['Matricola']}.txt",
            mime="text/plain"
        )
    else:
        st.write("Nessuno strumento disponibile.")

with colB:
    st.subheader("📜 Storico Interventi di Taratura")
    df_storico = carica_storico()
    if not df_storico.empty:
        st.dataframe(df_storico.iloc[::-1], use_container_width=True, hide_index=True)
    else:

        st.write("Nessuna taratura registrata finora nello storico.")
