from flask import Flask, request, jsonify, send_file, render_template_string
import pandas as pd
import unicodedata
from typing import Optional, Dict, List
from decimal import Decimal, ROUND_HALF_UP
import io
import base64
import os
from datetime import datetime

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== SEU CÓDIGO ORIGINAL (MANTIDO) ====================

UNIDADES_ALVO = [
    "ALTA FLORESTA", "ARAGUAIA", "CANARANA", "COLIDER", "COMODORO",
    "ITAPOA", "PALESTINA", "PIQUETE", "PONTES E LACERDA", "SAO GABRIEL"
]
HIDRO_KEY = "HIDROFORTE"
COLUNA_TIPO_CAMPANHA = 'whatsapp categoria'

UNIDADES_FORA_DO_RATEIO_USUARIOS = {"GESTAO SUL", "CENTRO SUL"}

ALIASES_GERAIS: Dict[str, str] = {
    "ALTA FLORESTA": "ALTA FLORESTA",
    "ARAGUAIA": "ARAGUAIA",
    "CANARANA": "CANARANA",
    "COLIDER": "COLIDER",
    "COLIDOR": "COLIDER",
    "COLÍDER": "COLIDER",
    "COMODORO": "COMODORO",
    "ITAPOA": "ITAPOA",
    "ITAPOA/SAO JOSE": "ITAPOA",
    "PALESTINA": "PALESTINA",
    "ESAP": "PALESTINA",
    "PIQUETE": "PIQUETE",
    "PONTES E LACERDA": "PONTES E LACERDA",
    "PONTES LACERDA": "PONTES E LACERDA",
    "SAO GABRIEL": "SAO GABRIEL",
    "SAO GABRIEL DO OESTE": "SAO GABRIEL",
    "GESTAO SUL": "GESTAO SUL",
    "GESTÃO SUL": "GESTAO SUL",
    "CENTRO SUL": "CENTRO SUL",
    "HIDROFORTE": HIDRO_KEY,
    "HIDRO FORTE": HIDRO_KEY,
}

# Mapeamento para nomes bonitos na planilha (MELHORIA)
NOMES_PLANILHA = {
    "ALTA FLORESTA": "ÁGUAS ALTA FLORESTA LTDA",
    "ARAGUAIA": "ARAGUAIA SANEAMENTO S.A - RDN",
    "CANARANA": "ÁGUAS CANARANA LTDA",
    "COLIDER": "ÁGUAS COLIDER LTDA",
    "COMODORO": "ÁGUAS COMODORO LTDA",
    "ITAPOA": "ITAPOÁ SANEAMENTO LTDA.",
    "PALESTINA": "EMPRESA DE SANEAMENTO DE PALESTINA - ESAP S/A",
    "PIQUETE": "ÁGUAS PIQUETE S.A.",
    "PONTES E LACERDA": "ÁGUAS PONTES E LACERDA LTDA",
    "SAO GABRIEL": "SÃO GABRIEL SANEAMENTO S.A"
}

# Valores unitários para cálculo do rateio em R$ (MELHORIA)
VALORES_UNITARIOS = {
    "mensagens_receptivas": 0.11,
    "licencas": 90.00,
    "atendimento_presencial": 1000.00,
    "whatsapp_marketing": 0.48,
    "whatsapp_utility": 0.14,
    "numero_oficial_waba": 400.00
}

def normalizar_texto(texto) -> str:
    if pd.isna(texto):
        return ""
    texto_nfd = unicodedata.normalize('NFD', str(texto))
    texto_limpo = "".join(c for c in texto_nfd if unicodedata.category(c) != 'Mn')
    return " ".join(texto_limpo.upper().strip().split())

def carregar_csv(caminho: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(caminho, sep=None, engine='python', encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
        return df
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {caminho}")
        return None
    except Exception as e:
        print(f"⚠️ Aviso: Não foi possível ler o ficheiro '{caminho}': {e}")
        return None

def escolher_coluna(df: pd.DataFrame, opcoes: List[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for opcao in opcoes:
        if opcao.lower() in cols:
            return opcao.lower()
    return None

def identificar_unidade(texto, contexto: str) -> Optional[str]:
    t = normalizar_texto(texto)
    if not t:
        return None
    for chave in sorted(ALIASES_GERAIS.keys(), key=len, reverse=True):
        chave_norm = normalizar_texto(chave)
        if chave_norm and chave_norm in t:
            unidade = ALIASES_GERAIS[chave]
            if contexto != 'USUÁRIOS' and unidade in UNIDADES_FORA_DO_RATEIO_USUARIOS:
                return None
            return unidade
    return None

def calcular_percentuais_fechando_100(contagem: pd.Series, unidades_validas: List[str]) -> Dict[str, float]:
    total_valido = sum(int(contagem.get(u, 0)) for u in unidades_validas)
    percentuais = {u: Decimal('0.00') for u in unidades_validas}
    if total_valido <= 0:
        return {u: float(v) for u, v in percentuais.items()}
    soma = Decimal('0.00')
    candidatas_ajuste = []
    total_decimal = Decimal(str(total_valido))
    for u in unidades_validas:
        qtd = int(contagem.get(u, 0))
        if qtd > 0:
            bruto = (Decimal(str(qtd)) / total_decimal) * Decimal('100')
            p = bruto.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            percentuais[u] = p
            soma += p
            candidatas_ajuste.append((u, qtd))
        else:
            percentuais[u] = Decimal('0.00')
    diferenca = Decimal('100.00') - soma
    if diferenca != Decimal('0.00') and candidatas_ajuste:
        unidade_ajuste = max(candidatas_ajuste, key=lambda x: (x[1], -unidades_validas.index(x[0])))[0]
        ajustado = percentuais[unidade_ajuste] + diferenca
        if ajustado < Decimal('0.00'):
            ajustado = Decimal('0.00')
        percentuais[unidade_ajuste] = ajustado.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    soma_final = sum(percentuais.values(), Decimal('0.00')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if soma_final != Decimal('100.00') and candidatas_ajuste:
        unidade_ajuste = max(candidatas_ajuste, key=lambda x: (x[1], -unidades_validas.index(x[0])))[0]
        percentuais[unidade_ajuste] = (percentuais[unidade_ajuste] + (Decimal('100.00') - soma_final)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {u: float(v) for u, v in percentuais.items()}

# ==================== FUNÇÕES MELHORADAS PARA API ====================

def processar_arquivo(caminho: str, coluna_unidade: str, nome_relatorio: str, filtros: Dict = None) -> Dict:
    """Processa um arquivo e retorna contagem e percentuais (MANTENDO LÓGICA ORIGINAL)"""
    df = carregar_csv(caminho)
    if df is None or df.empty:
        return {'contagem': {u: 0 for u in UNIDADES_ALVO}, 'percentuais': {u: 0.0 for u in UNIDADES_ALVO}, 'hidroforte': 0, 'nao_mapeado': 0}
    
    df = df.copy()
    df['unidade_match'] = df[coluna_unidade].apply(lambda x: identificar_unidade(x, nome_relatorio))
    
    # Aplicar filtros se existirem (como status=CONCLUIDO)
    if filtros:
        for col, valor in filtros.items():
            if col in df.columns:
                df = df[df[col].apply(normalizar_texto) == valor]
    
    contagem = df['unidade_match'].value_counts()
    percentuais = calcular_percentuais_fechando_100(contagem, UNIDADES_ALVO)
    
    return {
        'contagem': {u: int(contagem.get(u, 0)) for u in UNIDADES_ALVO},
        'percentuais': percentuais,
        'hidroforte': int(contagem.get(HIDRO_KEY, 0)),
        'nao_mapeado': int(df['unidade_match'].isna().sum())
    }

def gerar_excel_rateio(arquivos: Dict) -> io.BytesIO:
    """Gera Excel no formato do PDF (MELHORIA)"""
    
    # Salvar arquivos temporariamente
    caminhos = {}
    for nome, arquivo in arquivos.items():
        if arquivo:
            caminho = os.path.join(UPLOAD_FOLDER, f"{nome}_{datetime.now().timestamp()}.csv")
            arquivo.save(caminho)
            caminhos[nome] = caminho
    
    try:
        # 1. Processar Conversas (igual ao seu script)
        df_conv = carregar_csv(caminhos.get('conversas'))
        col_conv = escolher_coluna(df_conv, ['app integration id', 'unidade']) if df_conv is not None else None
        conversas = processar_arquivo(caminhos.get('conversas'), col_conv, 'CONVERSAS') if col_conv else {'contagem': {u:0 for u in UNIDADES_ALVO}}
        
        # 2. Processar Usuários
        df_user = carregar_csv(caminhos.get('usuarios'))
        col_etq = escolher_coluna(df_user, ['etiquetas']) if df_user is not None else None
        col_sit = escolher_coluna(df_user, ['situação', 'situacao']) if df_user is not None else None
        if col_etq and col_sit:
            df_user_filt = df_user[df_user[col_sit].apply(normalizar_texto) == 'ATIVO']
            temp_path = os.path.join(UPLOAD_FOLDER, f"temp_users.csv")
            df_user_filt.to_csv(temp_path, index=False)
            usuarios = processar_arquivo(temp_path, col_etq, 'USUÁRIOS')
            os.remove(temp_path)
        else:
            usuarios = {'contagem': {u:0 for u in UNIDADES_ALVO}}
        
        # 3. Processar Presencial
        df_pres = carregar_csv(caminhos.get('presencial'))
        col_status = escolher_coluna(df_pres, ['status']) if df_pres is not None else None
        col_empresa = escolher_coluna(df_pres, ['empresa']) if df_pres is not None else None
        if col_status and col_empresa:
            df_pres_filt = df_pres[df_pres[col_status].apply(normalizar_texto) == 'CONCLUIDO']
            temp_path = os.path.join(UPLOAD_FOLDER, f"temp_pres.csv")
            df_pres_filt.to_csv(temp_path, index=False)
            presencial = processar_arquivo(temp_path, col_empresa, 'PRESENCIAL')
            os.remove(temp_path)
        else:
            presencial = {'contagem': {u:0 for u in UNIDADES_ALVO}}
        
        # 4. Processar Campanhas Marketing
        marketing = {'contagem': {u:0 for u in UNIDADES_ALVO}}
        utility = {'contagem': {u:0 for u in UNIDADES_ALVO}}
        
        df_camp = carregar_csv(caminhos.get('campanhas'))
        if df_camp is not None:
            col_status = escolher_coluna(df_camp, ['status da chave'])
            col_dep = escolher_coluna(df_camp, ['departamento'])
            if col_status and col_dep:
                mask_status = df_camp[col_status].apply(normalizar_texto) == 'CONCLUIDO'
                df_filt = df_camp[mask_status].copy()
                
                if COLUNA_TIPO_CAMPANHA in df_filt.columns:
                    categorias = df_filt[COLUNA_TIPO_CAMPANHA].apply(normalizar_texto)
                    mask_mkt = categorias.str.contains('MARKETING', na=False)
                    mask_util = categorias.str.contains('UTILITY', na=False)
                    
                    temp_path = os.path.join(UPLOAD_FOLDER, f"temp_mkt.csv")
                    df_filt[mask_mkt].to_csv(temp_path, index=False)
                    marketing = processar_arquivo(temp_path, col_dep, 'CAMPANHAS')
                    os.remove(temp_path)
                    
                    temp_path = os.path.join(UPLOAD_FOLDER, f"temp_util.csv")
                    df_filt[mask_util].to_csv(temp_path, index=False)
                    utility = processar_arquivo(temp_path, col_dep, 'CAMPANHAS')
                    os.remove(temp_path)
        
        # ==================== MONTAR TABELAS ====================
        
        # Tabela 1: Percentuais (igual ao PDF)
        tabela_percentuais = []
        for unidade in UNIDADES_ALVO:
            tabela_percentuais.append({
                'Unidade': NOMES_PLANILHA.get(unidade, unidade),
                'Franquia (%)': 10.0,
                'Mensagens Receptivas (%)': conversas['percentuais'].get(unidade, 0),
                'Licenças Excedentes (%)': usuarios['percentuais'].get(unidade, 0),
                'Atendimento Presencial (%)': presencial['percentuais'].get(unidade, 0),
                'WhatsApp Marketing (%)': marketing['percentuais'].get(unidade, 0),
                'WhatsApp Utility (%)': utility['percentuais'].get(unidade, 0),
                'Número Oficial WhatsApp (%)': 10.0
            })
        
        # Calcular totais para rateio em R$
        total_conversas = sum(conversas['contagem'].values())
        total_usuarios = sum(usuarios['contagem'].values())
        total_presencial = sum(presencial['contagem'].values())
        total_marketing = sum(marketing['contagem'].values())
        total_utility = sum(utility['contagem'].values())
        total_waba = len(UNIDADES_ALVO)  # 1 por unidade
        
        valor_total_conversas = total_conversas * VALORES_UNITARIOS['mensagens_receptivas']
        valor_total_licencas = total_usuarios * VALORES_UNITARIOS['licencas']
        valor_total_presencial = total_presencial * VALORES_UNITARIOS['atendimento_presencial']
        valor_total_marketing = total_marketing * VALORES_UNITARIOS['whatsapp_marketing']
        valor_total_utility = total_utility * VALORES_UNITARIOS['whatsapp_utility']
        valor_total_waba = total_waba * VALORES_UNITARIOS['numero_oficial_waba']
        
        # Tabela 2: Valores em R$ (igual ao PDF)
        tabela_valores = []
        for unidade in UNIDADES_ALVO:
            pct_conv = conversas['percentuais'].get(unidade, 0) / 100
            pct_user = usuarios['percentuais'].get(unidade, 0) / 100
            pct_pres = presencial['percentuais'].get(unidade, 0) / 100
            pct_mkt = marketing['percentuais'].get(unidade, 0) / 100
            pct_util = utility['percentuais'].get(unidade, 0) / 100
            
            valor_franquia = 450.00
            valor_mensagens = pct_conv * valor_total_conversas
            valor_licencas = pct_user * valor_total_licencas
            valor_presencial = pct_pres * valor_total_presencial
            valor_marketing = pct_mkt * valor_total_marketing
            valor_utility = pct_util * valor_total_utility
            valor_waba = (10.0 / 100) * valor_total_waba  # 10% igual para todos
            
            total_unidade = (valor_franquia + valor_mensagens + valor_licencas + 
                           valor_presencial + valor_marketing + valor_utility + valor_waba)
            
            tabela_valores.append({
                'Unidade': NOMES_PLANILHA.get(unidade, unidade),
                'Franquia (R$)': round(valor_franquia, 2),
                'Mensagens Receptivas (R$)': round(valor_mensagens, 2),
                'Licenças Excedentes (R$)': round(valor_licencas, 2),
                'Atendimento Presencial (R$)': round(valor_presencial, 2),
                'WhatsApp Marketing (R$)': round(valor_marketing, 2),
                'WhatsApp Utility (R$)': round(valor_utility, 2),
                'Número Oficial WhatsApp (R$)': round(valor_waba, 2),
                'Total por Unidade (R$)': round(total_unidade, 2)
            })
        
        # Adicionar linha de total
        totais = {
            'Franquia (R$)': sum(v['Franquia (R$)'] for v in tabela_valores),
            'Mensagens Receptivas (R$)': sum(v['Mensagens Receptivas (R$)'] for v in tabela_valores),
            'Licenças Excedentes (R$)': sum(v['Licenças Excedentes (R$)'] for v in tabela_valores),
            'Atendimento Presencial (R$)': sum(v['Atendimento Presencial (R$)'] for v in tabela_valores),
            'WhatsApp Marketing (R$)': sum(v['WhatsApp Marketing (R$)'] for v in tabela_valores),
            'WhatsApp Utility (R$)': sum(v['WhatsApp Utility (R$)'] for v in tabela_valores),
            'Número Oficial WhatsApp (R$)': sum(v['Número Oficial WhatsApp (R$)'] for v in tabela_valores),
            'Total por Unidade (R$)': sum(v['Total por Unidade (R$)'] for v in tabela_valores)
        }
        
        # Gerar Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_pct = pd.DataFrame(tabela_percentuais)
            df_val = pd.DataFrame(tabela_valores)
            
            df_pct.to_excel(writer, sheet_name='Percentuais por Item', index=False)
            df_val.to_excel(writer, sheet_name='Rateio de Valores (R$)', index=False)
            
            # Ajustar largura das colunas
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    worksheet.column_dimensions[column_letter].width = min(max_length + 2, 35)
        
        output.seek(0)
        return output
        
    finally:
        for caminho in caminhos.values():
            if os.path.exists(caminho):
                os.remove(caminho)

# ==================== ROTAS DA API ====================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Rateio Norte Saneamento</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #1e3c72, #2a5298); min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; border-radius: 15px; padding: 30px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
        h1 { color: #1e3c72; text-align: center; }
        .upload-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .upload-card { border: 2px dashed #ccc; border-radius: 10px; padding: 20px; text-align: center; cursor: pointer; transition: all 0.3s; }
        .upload-card:hover { border-color: #2a5298; background: #f0f4ff; }
        .upload-card .icon { font-size: 40px; }
        .upload-card input { display: none; }
        .file-name { font-size: 12px; color: #28a745; margin-top: 10px; }
        button { background: linear-gradient(135deg, #1e3c72, #2a5298); color: white; border: none; padding: 12px 30px; border-radius: 8px; font-size: 16px; cursor: pointer; margin: 5px; }
        button:hover { transform: translateY(-2px); }
        .status { padding: 15px; border-radius: 8px; margin-top: 20px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
        .loading { display: none; text-align: center; padding: 20px; }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #2a5298; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>📊 Rateio Norte Saneamento - ABRIL/2026</h1>
            
            <div class="upload-grid">
                <div class="upload-card" onclick="document.getElementById('conversas').click()">
                    <div class="icon">💬</div>
                    <h3>Conversas</h3>
                    <p>conversas.csv</p>
                    <div class="file-name" id="conversas-name"></div>
                    <input type="file" id="conversas" accept=".csv">
                </div>
                <div class="upload-card" onclick="document.getElementById('campanhas').click()">
                    <div class="icon">📢</div>
                    <h3>Campanhas</h3>
                    <p>campanhas.csv</p>
                    <div class="file-name" id="campanhas-name"></div>
                    <input type="file" id="campanhas" accept=".csv">
                </div>
                <div class="upload-card" onclick="document.getElementById('presencial').click()">
                    <div class="icon">🏢</div>
                    <h3>Presencial</h3>
                    <p>presencial.csv</p>
                    <div class="file-name" id="presencial-name"></div>
                    <input type="file" id="presencial" accept=".csv">
                </div>
                <div class="upload-card" onclick="document.getElementById('usuarios').click()">
                    <div class="icon">👥</div>
                    <h3>Usuários</h3>
                    <p>usuarios.csv</p>
                    <div class="file-name" id="usuarios-name"></div>
                    <input type="file" id="usuarios" accept=".csv">
                </div>
            </div>
            
            <div style="text-align: center;">
                <button onclick="processar()">🚀 GERAR RATEIO</button>
            </div>
            
            <div id="loading" class="loading">
                <div class="spinner"></div>
                <p>Processando arquivos...</p>
            </div>
            
            <div id="status"></div>
        </div>
    </div>
    
    <script>
        // Mostrar nome dos arquivos
        ['conversas', 'campanhas', 'presencial', 'usuarios'].forEach(id => {
            document.getElementById(id).addEventListener('change', function(e) {
                const span = document.getElementById(id + '-name');
                if (this.files.length > 0) {
                    span.innerHTML = '✅ ' + this.files[0].name;
                } else {
                    span.innerHTML = '';
                }
            });
        });
        
        async function processar() {
            const formData = new FormData();
            const files = ['conversas', 'campanhas', 'presencial', 'usuarios'];
            let hasFiles = false;
            
            files.forEach(id => {
                const input = document.getElementById(id);
                if (input.files.length > 0) {
                    formData.append(id, input.files[0]);
                    hasFiles = true;
                }
            });
            
            if (!hasFiles) {
                mostrarStatus('❌ Selecione pelo menos um arquivo CSV', 'error');
                return;
            }
            
            document.getElementById('loading').style.display = 'block';
            document.getElementById('status').innerHTML = '';
            
            try {
                const response = await fetch('/api/rateio', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (data.success) {
                    mostrarStatus('✅ ' + data.mensagem, 'success');
                    // Baixar Excel
                    const link = document.createElement('a');
                    link.href = 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,' + data.excel;
                    link.download = 'rateio_norte_' + new Date().toISOString().slice(0,19).replace(/:/g, '-') + '.xlsx';
                    link.click();
                } else {
                    mostrarStatus('❌ ' + data.erro, 'error');
                }
            } catch (error) {
                mostrarStatus('❌ Erro: ' + error.message, 'error');
            } finally {
                document.getElementById('loading').style.display = 'none';
            }
        }
        
        function mostrarStatus(msg, tipo) {
            const div = document.getElementById('status');
            div.innerHTML = '<div class="status ' + tipo + '">' + msg + '</div>';
            setTimeout(() => { if (div.innerHTML === msg) div.innerHTML = ''; }, 5000);
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/rateio', methods=['POST'])
def api_rateio():
    """Endpoint da API que processa os arquivos e retorna Excel"""
    arquivos = {
        'conversas': request.files.get('conversas'),
        'campanhas': request.files.get('campanhas'),
        'presencial': request.files.get('presencial'),
        'usuarios': request.files.get('usuarios')
    }
    
    try:
        excel_file = gerar_excel_rateio(arquivos)
        excel_base64 = base64.b64encode(excel_file.getvalue()).decode('utf-8')
        
        return jsonify({
            'success': True,
            'excel': excel_base64,
            'mensagem': 'Rateio gerado com sucesso!'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'erro': str(e)
        }), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("📊 API RATEIO NORTE SANEAMENTO")
    print("🚀 Baseada no script percentuais_norte.py")
    print("📱 Acesse: http://localhost:5000")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)