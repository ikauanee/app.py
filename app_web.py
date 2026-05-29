from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import unicodedata
import os
import zipfile
from datetime import datetime
import io
import base64

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Criar pastas necessárias
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

ALIASES = {
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
}

# ==================== FUNÇÕES DE PROCESSAMENTO ====================

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

def processar_arquivo(caminho, coluna_alvo, colunas_para_filtrar=None):
    """Processa arquivo CSV e retorna contagem por unidade"""
    if not caminho or not os.path.exists(caminho):
        return {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}
    
    try:
        df = pd.read_csv(caminho, encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
        
        # Aplicar filtros se existirem
        if colunas_para_filtrar:
            for col, valor in colunas_para_filtrar.items():
                if col in df.columns:
                    df = df[df[col].apply(normalizar_texto) == valor]
        
        # Encontrar coluna alvo
        col_alvo = None
        for col in df.columns:
            if coluna_alvo.lower() in col:
                col_alvo = col
                break
        
        if not col_alvo:
            return {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}
        
        # Identificar unidades
        df['unidade'] = df[col_alvo].apply(identificar_unidade)
        contagem = df['unidade'].value_counts()
        
        resultado = {}
        for unidade in UNIDADES_CONFIG.keys():
            resultado[unidade] = int(contagem.get(unidade, 0))
        
        return resultado
        
    except Exception as e:
        print(f"Erro ao processar {caminho}: {e}")
        return {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}

def gerar_planilha(arquivos):
    """Gera planilha a partir dos arquivos enviados"""
    
    # Salvar arquivos temporariamente
    caminhos = {}
    for nome, arquivo in arquivos.items():
        if arquivo:
            caminho = os.path.join(app.config['UPLOAD_FOLDER'], f"{nome}_{datetime.now().timestamp()}.csv")
            arquivo.save(caminho)
            caminhos[nome] = caminho
    
    try:
        # Processar Conversas
        conversas_count = processar_arquivo(
            caminhos.get('conversas'), 
            'unidade'
        )
        
        # Processar Presencial (apenas CONCLUIDO)
        presencial_count = processar_arquivo(
            caminhos.get('presencial'),
            'empresa',
            {'status': 'CONCLUIDO'}
        )
        
        # Processar Usuários (apenas ATIVO)
        usuarios_count = processar_arquivo(
            caminhos.get('usuarios'),
            'etiquetas',
            {'situacao': 'ATIVO'}
        )
        
        # Processar Campanhas Utility (CONCLUIDO + UTILITY)
        utility_count = {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}
        if caminhos.get('campanhas'):
            try:
                df_camp = pd.read_csv(caminhos['campanhas'], encoding='utf-8-sig')
                df_camp.columns = df_camp.columns.str.strip().str.lower()
                
                # Filtrar CONCLUIDO
                if 'status da chave' in df_camp.columns:
                    df_camp = df_camp[df_camp['status da chave'].apply(normalizar_texto) == 'CONCLUIDO']
                
                # Filtrar UTILITY
                if 'whatsapp categoria' in df_camp.columns:
                    df_camp = df_camp[df_camp['whatsapp categoria'].apply(normalizar_texto).str.contains('UTILITY', na=False)]
                
                # Identificar unidades
                dep_col = 'departamento' if 'departamento' in df_camp.columns else 'unidade'
                if dep_col in df_camp.columns:
                    df_camp['unidade'] = df_camp[dep_col].apply(identificar_unidade)
                    contagem = df_camp['unidade'].value_counts()
                    for unidade in UNIDADES_CONFIG.keys():
                        utility_count[unidade] = int(contagem.get(unidade, 0))
            except Exception as e:
                print(f"Erro ao processar campanhas: {e}")
        
        # Montar planilha
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
        
        # Adicionar total
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
        
        # Gerar Excel em memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, sheet_name='Unidades Norte', index=False)
            
            # Ajustar largura das colunas
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
            'total_unidades': len(UNIDADES_CONFIG)
        }
        
    except Exception as e:
        return {'success': False, 'erro': str(e)}
    
    finally:
        # Limpar arquivos temporários
        for caminho in caminhos.values():
            if os.path.exists(caminho):
                os.remove(caminho)

# ==================== ROTAS DA API ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/processar', methods=['POST'])
def processar():
    """Endpoint para processar os arquivos e gerar planilha"""
    
    arquivos = {
        'conversas': request.files.get('conversas'),
        'campanhas': request.files.get('campanhas'),
        'presencial': request.files.get('presencial'),
        'usuarios': request.files.get('usuarios')
    }
    
    # Verificar se pelo menos um arquivo foi enviado
    if not any(arquivos.values()):
        return jsonify({'success': False, 'erro': 'Nenhum arquivo enviado'}), 400
    
    resultado = gerar_planilha(arquivos)
    
    if resultado['success']:
        # Salvar o Excel em memória para download
        excel_data = resultado['arquivo'].getvalue()
        
        return jsonify({
            'success': True,
            'excel_base64': base64.b64encode(excel_data).decode('utf-8'),
            'dados': resultado['dados'],
            'total_unidades': resultado['total_unidades'],
            'mensagem': 'Planilha gerada com sucesso!'
        })
    else:
        return jsonify({'success': False, 'erro': resultado.get('erro', 'Erro ao processar')}), 500

@app.route('/baixar_modelo', methods=['GET'])
def baixar_modelo():
    """Baixa arquivos modelo para exemplo"""
    
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Criar modelos CSV
        modelos = {
            'conversas_modelo.csv': pd.DataFrame({
                'unidade': ['ALTA FLORESTA', 'ITAPOA', 'PONTES E LACERDA'],
                'quantidade': [100, 200, 150]
            }),
            'campanhas_modelo.csv': pd.DataFrame({
                'departamento': ['ALTA FLORESTA', 'ITAPOA', 'HIDROFORTE'],
                'status da chave': ['CONCLUIDO', 'CONCLUIDO', 'PENDENTE'],
                'whatsapp categoria': ['MARKETING', 'UTILITY', 'UTILITY']
            }),
            'presencial_modelo.csv': pd.DataFrame({
                'empresa': ['ALTA FLORESTA', 'ITAPOA', 'PONTES E LACERDA'],
                'status': ['CONCLUIDO', 'CONCLUIDO', 'CONCLUIDO']
            }),
            'usuarios_modelo.csv': pd.DataFrame({
                'etiquetas': ['ALTA FLORESTA', 'ITAPOA', 'HIDROFORTE'],
                'situacao': ['ATIVO', 'ATIVO', 'ATIVO']
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
    print("\n" + "="*50)
    print("🚀 SERVIDOR INICIADO!")
    print("📱 Acesse no navegador: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)