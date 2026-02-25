import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pyairtable import Api

# Configurazione pagina
st.set_page_config(page_title="Registro Tarature", page_icon="📏", layout="wide")

# Connessione ad Airtable
api = Api(st.secrets["AIRTABLE_PAT"])
base_id = st.secrets["AIRTABLE_BASE_ID"]
tabella_registro = api.table(base_id, "Registro")
tabella_storico = api.table(base_id, "Storico")

# --- FUNZIONI DI LETTURA E SALVATAGGIO ---
def carica_registro():
    records = tabella_registro.all()
    dati = [{"id_airtable": r["id"], **r["fields"]} for r in records]
    df = pd.DataFrame(dati)
    
    if not df.empty:
        colonne_attese = ["id_airtable", "Matricola", "Strumento", "Modello", "Seriale costruttore", "Data Taratura", "Data Scadenza"]
        for col in colonne_attese:
            if col not in df.columns:
                df[col] = ""
                
        df['Matricola'] = df['Matricola'].astype(str).str.strip()
        # errors='coerce' previene i crash se Airtable ha celle vuote
        df['Data Taratura'] = pd.to_datetime(df['Data Taratura'], errors='coerce')
        df['Data Scadenza'] = pd.to_datetime(df['Data Scadenza'], errors='coerce')
    return df

def carica_storico():
    records = tabella_storico.all()
    dati = [r["fields"] for r in records]
    df = pd.DataFrame(dati)
    if not df.empty:
        if 'Data Taratura' in df.columns:
            df['Data Taratura'] = pd.to_datetime(df['Data Taratura'], errors='coerce')
        if 'Data Scadenza' in df.columns:
            df['Data Scadenza'] = pd.to_datetime(df['Data Scadenza'], errors='coerce')
    return df

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
with st.form("form_inserimento", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        matricola = st.text_input("Matricola / ID Interno")
        nome = st.text_input("Nome Strumento")
    with col2:
        modello = st.text_input("Marca e Modello")
        seriale = st.text_input("Seriale costruttore")
    with col3:
        data_tar = st.date_input("Data di esecuzione taratura", value=datetime.now().date())
        data_scad = st.date_input("Data di scadenza", value=datetime.now().date() + timedelta(days=365))
        
    inviato = st.form_submit_button("Salva Taratura")
    
    if inviato and matricola and nome:
        dati_record = {
            "Matricola": str(matricola).strip(),
            "Strumento": nome,
            "Modello": modello,
            "Seriale costruttore": seriale,
            "Data Taratura": data_tar.strftime("%Y-%m-%d"),
            "Data Scadenza": data_scad.strftime("%Y-%m-%d")
        }
        
        # Aggiornamento o Creazione
        if not df_registro.empty and matricola in df_registro['Matricola'].values:
            id_da_aggiornare = df_registro[df_registro['Matricola'] == matricola].iloc[0]['id_airtable']
            tabella_registro.update(id_da_aggiornare, dati_record)
            st.success(f"Taratura aggiornata per lo strumento: {matricola}")
        else:
            tabella_registro.create(dati_record)
            st.success(f"Nuovo strumento inserito: {matricola}")
            
        # Storico
        tabella_storico.create({
            "Data Registrazione": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Matricola": str(matricola).strip(),
            "Strumento": nome,
            "Data Taratura": data_tar.strftime("%Y-%m-%d"),
            "Data Scadenza": data_scad.strftime("%Y-%m-%d")
        })
        st.rerun()

st.divider()

# 3. VISUALIZZAZIONE REGISTRO (Ora senza orari!)
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
            
    # Formattiamo le date per mostrare solo Giorno/Mese/Anno
    st.dataframe(
        df_vista.style
        .apply(evidenzia_scadenze, axis=1)
        .format({
            "Data Taratura": lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else "",
            "Data Scadenza": lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else ""
        }),
        use_container_width=True, 
        hide_index=True
    )
else:
    st.info("Il registro è vuoto.")

st.divider()

# 4. CREAZIONE RAPPORTO E STORICO
colA, colB = st.columns([1, 1])

with colA:
    st.subheader("📄 Genera Rapporto di Taratura")
    
    # Ignora le righe vuote o senza matricola che arrivano da Airtable
    df_valido = df_registro[(df_registro['Matricola'] != "") & (df_registro['Matricola'].notna())].copy()
    
    if not df_valido.empty:
        lista_strumenti = df_valido['Strumento'].fillna("Sconosciuto") + " (Matr: " + df_valido['Matricola'] + ")"
        scelta = st.selectbox("Seleziona lo strumento:", lista_strumenti)
        
        matr_selezionata = scelta.split("(Matr: ")[1].replace(")", "")
        dati_strumento = df_valido[df_valido['Matricola'] == matr_selezionata].iloc[0]
        
        if pd.notna(dati_strumento['Data Scadenza']) and dati_strumento['Data Scadenza'] < oggi:
            stato = "SCADUTO"
        else:
            stato = "IN CORSO DI VALIDITÀ"
            
        # Formattazione sicura delle date per il file di testo (Risolve il NameError!)
        dt_tar = dati_strumento['Data Taratura']
        dt_scad = dati_strumento['Data Scadenza']
        str_tar = dt_tar.strftime('%d/%m/%Y') if pd.notna(dt_tar) else "N/D"
        str_scad = dt_scad.strftime('%d/%m/%Y') if pd.notna(dt_scad) else "N/D"
        
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
Data di generazione: {datetime.now().strftime("%d/%m/%Y")}
Firma del Responsabile: _______________________
"""
        st.download_button(
            label="⬇️ Scarica Rapporto (.txt)",
            data=testo_rapporto,
            file_name=f"Rapporto_Taratura_{dati_strumento['Matricola']}.txt",
            mime="text/plain"
        )
    else:
        st.write("Nessuno strumento valido disponibile.")

with colB:
    st.subheader("📜 Storico Interventi di Taratura")
    df_storico = carica_storico()
    if not df_storico.empty:
        # Applichiamo la stessa formattazione per nascondere l'orario anche qui
        colonne_da_formattare = {}
        if 'Data Taratura' in df_storico.columns:
            colonne_da_formattare["Data Taratura"] = lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else ""
        if 'Data Scadenza' in df_storico.columns:
            colonne_da_formattare["Data Scadenza"] = lambda x: x.strftime('%d/%m/%Y') if pd.notna(x) else ""
            
        st.dataframe(
            df_storico.iloc[::-1].style.format(colonne_da_formattare), 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.write("Nessuna taratura registrata finora nello storico.")
