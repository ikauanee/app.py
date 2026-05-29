from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import unicodedata
import os
import zipfile
from datetime import datetime
import io
import base64
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('templates', exist_ok=True)

# ==================== CONFIGURAÇÕES ====================

UNIDADES_CONFIG = {
    "ALTA FLORESTA": {"nome_planilha": "Alta Floresta", "franquia": 1000},
    "ARAGUAIA": {"nome_planilha": "Araguaia", "franquia": 900},
    "CANARANA": {"nome_planilha": "Canarana", "franquia": 800},
    "COLIDER": {"nome_planilha": "Colíder", "franquia": 850},
    "COMODORO": {"nome_planilha": "Comodoro", "franquia": 750},
    "ITAPOA": {"nome_planilha": "Itapoã", "franquia": 950},
    "PALESTINA": {"nome_planilha": "Palestina", "franquia": 700},
    "PIQUETE": {"nome_planilha": "Piqueté", "franquia": 650},
    "PONTES E LACERDA": {"nome_planilha": "Pontes e Lacerda", "franquia": 1100},
    "SAO GABRIEL": {"nome_planilha": "São Gabriel", "franquia": 800}
}

# Aliases expandidos para capturar mais variações
ALIASES = {
    # Alta Floresta
    "ALTA FLORESTA": "ALTA FLORESTA",
    "ALTA FLORESTA D'OESTE": "ALTA FLORESTA",
    "ALTA": "ALTA FLORESTA",
    
    # Araguaia
    "ARAGUAIA": "ARAGUAIA",
    "ARAGUAIA - MT": "ARAGUAIA",
    
    # Canarana
    "CANARANA": "CANARANA",
    "CANARANA - MT": "CANARANA",
    
    # Colider
    "COLIDER": "COLIDER",
    "COLIDOR": "COLIDER",
    "COLÍDER": "COLIDER",
    
    # Comodoro
    "COMODORO": "COMODORO",
    
    # Itapoa
    "ITAPOA": "ITAPOA",
    "ITAPOA/SAO JOSE": "ITAPOA",
    "ITAPOÃ": "ITAPOA",
    "ITAPOA DO OESTE": "ITAPOA",
    
    # Palestina
    "PALESTINA": "PALESTINA",
    "ESAP": "PALESTINA",
    
    # Piquete
    "PIQUETE": "PIQUETE",
    "PIQUETÉ": "PIQUETE",
    
    # Pontes e Lacerda
    "PONTES E LACERDA": "PONTES E LACERDA",
    "PONTES LACERDA": "PONTES E LACERDA",
    "PONTES": "PONTES E LACERDA",
    
    # Sao Gabriel
    "SAO GABRIEL": "SAO GABRIEL",
    "SAO GABRIEL DO OESTE": "SAO GABRIEL",
    "SÃO GABRIEL": "SAO GABRIEL",
    
    # HIDROFORTE (ignorar no cálculo)
    "HIDROFORTE": "HIDROFORTE",
    "HIDRO FORTE": "HIDROFORTE",
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
    
    # Debug: print o que está sendo identificado
    print(f"🔍 Identificando: '{t}'")
    
    for chave in sorted(ALIASES.keys(), key=len, reverse=True):
        chave_norm = normalizar_texto(chave)
        if chave_norm and chave_norm in t:
            unidade = ALIASES[chave]
            print(f"   ✅ Match: '{chave}' -> {unidade}")
            return unidade
    
    print(f"   ❌ Sem match para: '{t}'")
    return None

def processar_arquivo_detalhado(caminho, coluna_alvo, nome_arquivo, colunas_para_filtrar=None):
    """Processa arquivo e retorna contagem com debug"""
    if not caminho or not os.path.exists(caminho):
        print(f"⚠️ Arquivo não encontrado: {caminho}")
        return {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}
    
    try:
        print(f"\n📄 Processando {nome_arquivo}...")
        df = pd.read_csv(caminho, encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
        print(f"   Colunas encontradas: {list(df.columns)}")
        print(f"   Total de linhas: {len(df)}")
        
        # Aplicar filtros
        if colunas_para_filtrar:
            for col, valor in colunas_para_filtrar.items():
                if col in df.columns:
                    antes = len(df)
                    df[col + '_norm'] = df[col].apply(normalizar_texto)
                    df = df[df[col + '_norm'] == valor]
                    print(f"   Filtro {col}={valor}: {antes} -> {len(df)} linhas")
        
        # Encontrar coluna alvo
        col_alvo = None
        for col in df.columns:
            if coluna_alvo.lower() in col:
                col_alvo = col
                break
        
        if not col_alvo:
            print(f"   ❌ Coluna '{coluna_alvo}' não encontrada!")
            return {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}
        
        print(f"   Coluna alvo: {col_alvo}")
        print(f"   Valores únicos na coluna: {df[col_alvo].head(10).tolist()}")
        
        # Identificar unidades
        df['unidade'] = df[col_alvo].apply(identificar_unidade)
        
        # Estatísticas
        total_identificadas = df['unidade'].notna().sum()
        nao_identificadas = df['unidade'].isna().sum()
        print(f"   Identificadas: {total_identificadas}")
        print(f"   Não identificadas: {nao_identificadas}")
        
        # Mostrar exemplos não identificados
        if nao_identificadas > 0:
            exemplos = df[df['unidade'].isna()][col_alvo].head(5).tolist()
            print(f"   Exemplos não identificados: {exemplos}")
        
        contagem = df['unidade'].value_counts()
        
        resultado = {}
        for unidade in UNIDADES_CONFIG.keys():
            resultado[unidade] = int(contagem.get(unidade, 0))
            if resultado[unidade] > 0:
                print(f"   📊 {unidade}: {resultado[unidade]}")
        
        # Mostrar HIDROFORTE (ignorado)
        hidro = int(contagem.get('HIDROFORTE', 0))
        if hidro > 0:
            print(f"   ⚠️ HIDROFORTE (ignorado): {hidro}")
        
        return resultado
        
    except Exception as e:
        print(f"   ❌ Erro: {e}")
        return {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}

def gerar_planilha_com_debug(arquivos):
    """Gera planilha com debug detalhado"""
    
    print("\n" + "="*60)
    print("🚀 INICIANDO PROCESSAMENTO")
    print("="*60)
    
    caminhos = {}
    for nome, arquivo in arquivos.items():
        if arquivo:
            caminho = os.path.join(app.config['UPLOAD_FOLDER'], f"{nome}_{datetime.now().timestamp()}.csv")
            arquivo.save(caminho)
            caminhos[nome] = caminho
            print(f"📁 Arquivo salvo: {nome} -> {caminho}")
    
    try:
        # Processar Conversas
        conversas_count = processar_arquivo_detalhado(
            caminhos.get('conversas'), 
            'unidade',
            'conversas.csv'
        )
        
        # Processar Presencial
        presencial_count = processar_arquivo_detalhado(
            caminhos.get('presencial'),
            'empresa',
            'presencial.csv',
            {'status': 'CONCLUIDO'}
        )
        
        # Processar Usuários
        usuarios_count = processar_arquivo_detalhado(
            caminhos.get('usuarios'),
            'etiquetas',
            'usuarios.csv',
            {'situacao': 'ATIVO'}
        )
        
        # Processar Campanhas Utility
        utility_count = {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}
        if caminhos.get('campanhas'):
            try:
                print(f"\n📄 Processando campanhas.csv...")
                df_camp = pd.read_csv(caminhos['campanhas'], encoding='utf-8-sig')
                df_camp.columns = df_camp.columns.str.strip().str.lower()
                print(f"   Colunas: {list(df_camp.columns)}")
                print(f"   Total linhas: {len(df_camp)}")
                
                # Filtrar CONCLUIDO
                if 'status da chave' in df_camp.columns:
                    antes = len(df_camp)
                    df_camp['status_norm'] = df_camp['status da chave'].apply(normalizar_texto)
                    df_camp = df_camp[df_camp['status_norm'] == 'CONCLUIDO']
                    print(f"   Filtro CONCLUIDO: {antes} -> {len(df_camp)}")
                
                # Filtrar UTILITY
                if 'whatsapp categoria' in df_camp.columns:
                    antes = len(df_camp)
                    df_camp['cat_norm'] = df_camp['whatsapp categoria'].apply(normalizar_texto)
                    df_camp = df_camp[df_camp['cat_norm'].str.contains('UTILITY', na=False)]
                    print(f"   Filtro UTILITY: {antes} -> {len(df_camp)}")
                
                # Identificar unidades
                dep_col = 'departamento' if 'departamento' in df_camp.columns else 'unidade'
                if dep_col in df_camp.columns:
                    print(f"   Valores únicos em {dep_col}: {df_camp[dep_col].head(10).tolist()}")
                    df_camp['unidade'] = df_camp[dep_col].apply(identificar_unidade)
                    contagem = df_camp['unidade'].value_counts()
                    for unidade in UNIDADES_CONFIG.keys():
                        utility_count[unidade] = int(contagem.get(unidade, 0))
                        if utility_count[unidade] > 0:
                            print(f"   📊 UTILITY {unidade}: {utility_count[unidade]}")
            except Exception as e:
                print(f"   ❌ Erro campanhas: {e}")
        
        # Montar planilha
        print("\n" + "="*60)
        print("📊 MONTANDO PLANILHA FINAL")
        print("="*60)
        
        dados = []
        for unidade_interna, config in UNIDADES_CONFIG.items():
            conversas = conversas_count.get(unidade_interna, 0)
            franquia = config['franquia']
            excedente = max(0, conversas - franquia)
            
            dados.append({
                'Unidade': config['nome_planilha'],
                'Franquia': franquia,
                'Mensagens Receptivas Excedentes': excedente,
                'Atendimento presencial': presencial_count.get(unidade_interna, 0),
                'Whatsapp utility': utility_count.get(unidade_interna, 0),
                'numero oficial whatsapp (waba)': usuarios_count.get(unidade_interna, 0)
            })
            
            print(f"\n{config['nome_planilha']}:")
            print(f"   Conversas: {conversas}")
            print(f"   Franquia: {franquia}")
            print(f"   Excedente: {excedente}")
            print(f"   Presencial: {presencial_count.get(unidade_interna, 0)}")
            print(f"   Utility: {utility_count.get(unidade_interna, 0)}")
            print(f"   Usuários: {usuarios_count.get(unidade_interna, 0)}")
        
        df_final = pd.DataFrame(dados)
        total_row = {
            'Unidade': 'TOTAL',
            'Franquia': df_final['Franquia'].sum(),
            'Mensagens Receptivas Excedentes': df_final['Mensagens Receptivas Excedentes'].sum(),
            'Atendimento presencial': df_final['Atendimento presencial'].sum(),
            'Whatsapp utility': df_final['Whatsapp utility'].sum(),
            'numero oficial whatsapp (waba)': df_final['numero oficial whatsapp (waba)'].sum()
        }
        df_final = pd.concat([df_final, pd.DataFrame([total_row])], ignore_index=True)
        
        # Gerar Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, sheet_name='Unidades Norte', index=False)
            
            worksheet = writer.sheets['Unidades Norte']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 30)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        return {
            'success': True,
            'arquivo': output,
            'dados': df_final.to_dict('records'),
            'debug': {
                'conversas': conversas_count,
                'presencial': presencial_count,
                'utility': utility_count,
                'usuarios': usuarios_count
            }
        }
        
    except Exception as e:
        print(f"❌ ERRO GERAL: {e}")
        return {'success': False, 'erro': str(e)}
    
    finally:
        for caminho in caminhos.values():
            if os.path.exists(caminho):
                os.remove(caminho)
                print(f"🗑️ Arquivo removido: {caminho}")

# ==================== ROTAS ====================

@app.route('/')
def index():
    return render_template('index.html')

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
    
    resultado = gerar_planilha_com_debug(arquivos)
    
    if resultado['success']:
        excel_data = resultado['arquivo'].getvalue()
        
        return jsonify({
            'success': True,
            'excel_base64': base64.b64encode(excel_data).decode('utf-8'),
            'dados': resultado['dados'],
            'debug': resultado.get('debug', {}),
            'mensagem': 'Planilha gerada com sucesso!'
        })
    else:
        return jsonify({'success': False, 'erro': resultado.get('erro', 'Erro ao processar')}), 500

@app.route('/baixar_modelo', methods=['GET'])
def baixar_modelo():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
        modelos = {
            'conversas_modelo.csv': pd.DataFrame({
                'unidade': ['ALTA FLORESTA', 'ITAPOA', 'PONTES E LACERDA', 'HIDROFORTE'],
                'quantidade': [7228, 8591, 6662, 14746]
            }),
            'campanhas_modelo.csv': pd.DataFrame({
                'departamento': ['PONTES E LACERDA', 'ALTA FLORESTA', 'COLIDER', 'HIDROFORTE'],
                'status da chave': ['CONCLUIDO', 'CONCLUIDO', 'CONCLUIDO', 'CONCLUIDO'],
                'whatsapp categoria': ['MARKETING', 'UTILITY', 'UTILITY', 'UTILITY']
            }),
            'presencial_modelo.csv': pd.DataFrame({
                'empresa': ['ALTA FLORESTA', 'ITAPOA', 'PONTES E LACERDA', 'CANARANA'],
                'status': ['CONCLUIDO', 'CONCLUIDO', 'CONCLUIDO', 'CONCLUIDO']
            }),
            'usuarios_modelo.csv': pd.DataFrame({
                'etiquetas': ['ALTA FLORESTA', 'ITAPOA', 'PONTES E LACERDA', 'SAO GABRIEL', 'HIDROFORTE'],
                'situacao': ['ATIVO', 'ATIVO', 'ATIVO', 'ATIVO', 'ATIVO']
            })
        }
        
        for nome, df in modelos.items():
            csv_buffer = io.BytesIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_buffer.seek(0)
            zipf.writestr(nome, csv_buffer.getvalue())
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/zip',
        as_attachment=True,
        download_name='modelos_csv.zip'
    )

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 SERVIDOR INICIADO - MODO DEBUG")
    print("📱 Acesse: http://localhost:5000")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)