from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import unicodedata
import os
import zipfile
from datetime import datetime
import io
import base64
from decimal import Decimal, ROUND_HALF_UP

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('templates', exist_ok=True)

UNIDADES_CONFIG = {
    "ALTA FLORESTA": {"nome_planilha": "ÁGUAS ALTA FLORESTA LTDA", "nome_curto": "ALTA FLORESTA", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "ARAGUAIA": {"nome_planilha": "ARAGUAIA SANEAMENTO S.A - RDN", "nome_curto": "ARAGUAIA", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "CANARANA": {"nome_planilha": "ÁGUAS CANARANA LTDA", "nome_curto": "CANARANA", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "COLIDER": {"nome_planilha": "ÁGUAS COLIDER LTDA", "nome_curto": "COLIDER", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "COMODORO": {"nome_planilha": "ÁGUAS COMODORO LTDA", "nome_curto": "COMODORO", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "PALESTINA": {"nome_planilha": "EMPRESA DE SANEAMENTO DE PALESTINA - ESAP S/A", "nome_curto": "PALESTINA", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "PIQUETE": {"nome_planilha": "ÁGUAS PIQUETE S.A.", "nome_curto": "PIQUETE", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "PONTES E LACERDA": {"nome_planilha": "ÁGUAS PONTES E LACERDA LTDA", "nome_curto": "PONTES E LACERDA", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "ITAPOA": {"nome_planilha": "ITAPOÁ SANEAMENTO LTDA.", "nome_curto": "ITAPOA", "franquia_percentual": 10.0, "franquia_valor": 450.00},
    "SAO GABRIEL": {"nome_planilha": "SÃO GABRIEL SANEAMENTO S.A", "nome_curto": "SAO GABRIEL", "franquia_percentual": 10.0, "franquia_valor": 450.00}
}

VALORES_UNITARIOS = {
    "mensagens_receptivas": 0.11,
    "licencas": 90.00,
    "atendimento_presencial": 1000.00,
    "whatsapp_marketing": 0.48,
    "whatsapp_utility": 0.14,
    "numero_oficial_waba": 400.00
}

ALIASES = {
    "ALTA FLORESTA": "ALTA FLORESTA", "ALTA FLORESTA D'OESTE": "ALTA FLORESTA",
    "ARAGUAIA": "ARAGUAIA", "ARAGUAIA - MT": "ARAGUAIA",
    "CANARANA": "CANARANA", "CANARANA - MT": "CANARANA",
    "COLIDER": "COLIDER", "COLIDOR": "COLIDER", "COLÍDER": "COLIDER",
    "COMODORO": "COMODORO",
    "ITAPOA": "ITAPOA", "ITAPOA/SAO JOSE": "ITAPOA", "ITAPOÃ": "ITAPOA",
    "PALESTINA": "PALESTINA", "ESAP": "PALESTINA",
    "PIQUETE": "PIQUETE", "PIQUETÉ": "PIQUETE",
    "PONTES E LACERDA": "PONTES E LACERDA", "PONTES LACERDA": "PONTES E LACERDA",
    "SAO GABRIEL": "SAO GABRIEL", "SÃO GABRIEL": "SAO GABRIEL",
    "HIDROFORTE": "HIDROFORTE",
}
def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto_nfd = unicodedata.normalize('NFD', str(texto))
    texto_limpo = "".join(c for c in texto_nfd if unicodedata.category(c) != 'Mn')
    return " ".join(texto_limpo.upper().strip().split())

def identificar_unidade(texto):
    t = normalizar_texto(texto)
    if not t:
        return None
    for chave in sorted(ALIASES.keys(), key=len, reverse=True):
        chave_norm = normalizar_texto(chave)
        if chave_norm and chave_norm in t:
            return ALIASES[chave]
    return None

def processar_csv(caminho, coluna_alvo, filtros=None):
    if not caminho or not os.path.exists(caminho):
        return {u: 0 for u in UNIDADES_CONFIG.keys()}
    try:
        df = pd.read_csv(caminho, encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
        if filtros:
            for col, valor in filtros.items():
                if col in df.columns:
                    df[col + '_norm'] = df[col].apply(normalizar_texto)
                    df = df[df[col + '_norm'] == valor]
        col_alvo = None
        for col in df.columns:
            if coluna_alvo.lower() in col:
                col_alvo = col
                break
        if not col_alvo:
            return {u: 0 for u in UNIDADES_CONFIG.keys()}
        df['unidade'] = df[col_alvo].apply(identificar_unidade)
        contagem = df['unidade'].value_counts()
        resultado = {}
        for unidade in UNIDADES_CONFIG.keys():
            resultado[unidade] = int(contagem.get(unidade, 0))
        return resultado
    except Exception as e:
        print(f"Erro: {e}")
        return {u: 0 for u in UNIDADES_CONFIG.keys()}
def gerar_relatorio_completo(arquivos):
    caminhos = {}
    for nome, arquivo in arquivos.items():
        if arquivo:
            caminho = os.path.join(app.config['UPLOAD_FOLDER'], f"{nome}_{datetime.now().timestamp()}.csv")
            arquivo.save(caminho)
            caminhos[nome] = caminho
    try:
        conversas_count = processar_csv(caminhos.get('conversas'), 'unidade')
        total_conversas = sum(conversas_count.values())
        usuarios_count = processar_csv(caminhos.get('usuarios'), 'etiquetas', {'situacao': 'ATIVO'})
        total_usuarios = sum(usuarios_count.values())
        presencial_count = processar_csv(caminhos.get('presencial'), 'empresa', {'status': 'CONCLUIDO'})
        total_presencial = sum(presencial_count.values())
        
        marketing_count = {u: 0 for u in UNIDADES_CONFIG.keys()}
        utility_count = {u: 0 for u in UNIDADES_CONFIG.keys()}
        total_marketing = 0
        total_utility = 0
        
        if caminhos.get('campanhas'):
            try:
                df_camp = pd.read_csv(caminhos['campanhas'], encoding='utf-8-sig')
                df_camp.columns = df_camp.columns.str.strip().str.lower()
                if 'status da chave' in df_camp.columns:
                    df_camp['status_norm'] = df_camp['status da chave'].apply(normalizar_texto)
                    df_camp = df_camp[df_camp['status_norm'] == 'CONCLUIDO']
                dep_col = 'departamento' if 'departamento' in df_camp.columns else 'unidade'
                if 'whatsapp categoria' in df_camp.columns:
                    df_camp['cat_norm'] = df_camp['whatsapp categoria'].apply(normalizar_texto)
                    df_mkt = df_camp[df_camp['cat_norm'].str.contains('MARKETING', na=False)]
                    df_util = df_camp[df_camp['cat_norm'].str.contains('UTILITY', na=False)]
                    if dep_col in df_mkt.columns:
                        df_mkt['unidade'] = df_mkt[dep_col].apply(identificar_unidade)
                        contagem = df_mkt['unidade'].value_counts()
                        for u in UNIDADES_CONFIG.keys():
                            marketing_count[u] = int(contagem.get(u, 0))
                        total_marketing = sum(marketing_count.values())
                    if dep_col in df_util.columns:
                        df_util['unidade'] = df_util[dep_col].apply(identificar_unidade)
                        contagem = df_util['unidade'].value_counts()
                        for u in UNIDADES_CONFIG.keys():
                            utility_count[u] = int(contagem.get(u, 0))
                        total_utility = sum(utility_count.values())
            except Exception as e:
                print(f"Erro campanhas: {e}")
        
        waba_count = {u: 1 for u in UNIDADES_CONFIG.keys()}
        total_waba = sum(waba_count.values())
        
        def calc_percentuais(contagem, total):
            if total <= 0:
                return {u: 0.0 for u in contagem.keys()}
            pcts = {}
            soma = 0.0
            for u, v in contagem.items():
                p = (v / total) * 100
                pcts[u] = round(p, 2)
                soma += pcts[u]
            dif = round(100 - soma, 2)
            if abs(dif) > 0.01 and pcts:
                max_u = max(pcts.items(), key=lambda x: x[1])[0]
                pcts[max_u] = round(pcts[max_u] + dif, 2)
            return pcts
        
        conv_pct = calc_percentuais(conversas_count, total_conversas)
        user_pct = calc_percentuais(usuarios_count, total_usuarios)
        pres_pct = calc_percentuais(presencial_count, total_presencial)
        mkt_pct = calc_percentuais(marketing_count, total_marketing)
        util_pct = calc_percentuais(utility_count, total_utility)
        waba_pct = calc_percentuais(waba_count, total_waba)
        
        valor_total_mensagens = total_conversas * VALORES_UNITARIOS['mensagens_receptivas']
        valor_total_licencas = total_usuarios * VALORES_UNITARIOS['licencas']
        valor_total_presencial = total_presencial * VALORES_UNITARIOS['atendimento_presencial']
        valor_total_marketing = total_marketing * VALORES_UNITARIOS['whatsapp_marketing']
        valor_total_utility = total_utility * VALORES_UNITARIOS['whatsapp_utility']
        valor_total_waba = total_waba * VALORES_UNITARIOS['numero_oficial_waba']
        
        tabela_percentuais = []
        tabela_valores = []
        for unidade, config in UNIDADES_CONFIG.items():
            tabela_percentuais.append({
                'Unidade': config['nome_planilha'],
                'Franquia (%)': config['franquia_percentual'],
                'Mensagens Receptivas (%)': conv_pct.get(unidade, 0),
                'Licenças Excedentes (%)': user_pct.get(unidade, 0),
                'Atendimento Presencial (%)': pres_pct.get(unidade, 0),
                'WhatsApp Marketing (%)': mkt_pct.get(unidade, 0),
                'WhatsApp Utility (%)': util_pct.get(unidade, 0),
                'Número Oficial WhatsApp (%)': waba_pct.get(unidade, 0)
            })
            valor_franquia = config['franquia_valor']
            valor_mensagens = (conv_pct.get(unidade, 0) / 100) * valor_total_mensagens
            valor_licencas = (user_pct.get(unidade, 0) / 100) * valor_total_licencas
            valor_presencial = (pres_pct.get(unidade, 0) / 100) * valor_total_presencial
            valor_marketing = (mkt_pct.get(unidade, 0) / 100) * valor_total_marketing
            valor_utility = (util_pct.get(unidade, 0) / 100) * valor_total_utility
            valor_waba = (waba_pct.get(unidade, 0) / 100) * valor_total_waba
            total_unidade = valor_franquia + valor_mensagens + valor_licencas + valor_presencial + valor_marketing + valor_utility + valor_waba
            tabela_valores.append({
                'Unidade': config['nome_planilha'],
                'Franquia (R$)': round(valor_franquia, 2),
                'Mensagens Receptivas (R$)': round(valor_mensagens, 2),
                'Licenças Excedentes (R$)': round(valor_licencas, 2),
                'Atendimento Presencial (R$)': round(valor_presencial, 2),
                'WhatsApp Marketing (R$)': round(valor_marketing, 2),
                'WhatsApp Utility (R$)': round(valor_utility, 2),
                'Número Oficial WhatsApp (R$)': round(valor_waba, 2),
                'Total por Unidade (R$)': round(total_unidade, 2)
            })
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(tabela_percentuais).to_excel(writer, sheet_name='Percentuais por Item', index=False)
            pd.DataFrame(tabela_valores).to_excel(writer, sheet_name='Rateio de Valores', index=False)
        
        output.seek(0)
        return {'success': True, 'arquivo': output, 'tabela_percentuais': tabela_percentuais, 'tabela_valores': tabela_valores}
    except Exception as e:
        return {'success': False, 'erro': str(e)}
    finally:
        for caminho in caminhos.values():
            if os.path.exists(caminho):
                os.remove(caminho)
@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Rateio Norte Saneamento</title></head>
    <body style="font-family: Arial; padding: 20px;">
        <h1>📊 Rateio Norte Saneamento</h1>
        <form id="uploadForm" enctype="multipart/form-data">
            <div style="margin: 10px 0;">
                <label>📄 Conversas: <input type="file" name="conversas" accept=".csv"></label>
            </div>
            <div style="margin: 10px 0;">
                <label>📢 Campanhas: <input type="file" name="campanhas" accept=".csv"></label>
            </div>
            <div style="margin: 10px 0;">
                <label>🏢 Presencial: <input type="file" name="presencial" accept=".csv"></label>
            </div>
            <div style="margin: 10px 0;">
                <label>👥 Usuários: <input type="file" name="usuarios" accept=".csv"></label>
            </div>
            <button type="submit">🚀 Gerar Rateio</button>
        </form>
        <div id="result"></div>
        <script>
            document.getElementById('uploadForm').onsubmit = async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                const response = await fetch('/processar', {method: 'POST', body: formData});
                const data = await response.json();
                if (data.success) {
                    const link = document.createElement('a');
                    link.href = `data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${data.excel_base64}`;
                    link.download = 'rateio_norte.xlsx';
                    link.click();
                    document.getElementById('result').innerHTML = '<p style="color: green;">✅ Rateio gerado com sucesso!</p>';
                } else {
                    document.getElementById('result').innerHTML = `<p style="color: red;">❌ Erro: ${data.erro}</p>`;
                }
            };
        </script>
    </body>
    </html>
    '''

@app.route('/processar', methods=['POST'])
def processar():
    arquivos = {
        'conversas': request.files.get('conversas'),
        'campanhas': request.files.get('campanhas'),
        'presencial': request.files.get('presencial'),
        'usuarios': request.files.get('usuarios')
    }
    if not any(arquivos.values()):
        return jsonify({'success': False, 'erro': 'Nenhum arquivo enviado'}), 400
    resultado = gerar_relatorio_completo(arquivos)
    if resultado['success']:
        excel_data = resultado['arquivo'].getvalue()
        return jsonify({'success': True, 'excel_base64': base64.b64encode(excel_data).decode('utf-8')})
    else:
        return jsonify({'success': False, 'erro': resultado.get('erro', 'Erro')}), 500

if __name__ == '__main__':
    print("🚀 Servidor: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
