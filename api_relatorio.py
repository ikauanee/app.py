# api_relatorio.py
from flask import Flask, request, jsonify, send_file
import pandas as pd
import unicodedata
from typing import Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP
import io
import os
from werkzeug.utils import secure_filename
import tempfile
import zipfile

app = Flask(__name__)

# ==================== CONFIGURAÇÕES ====================
UNIDADES_ALVO = [
    "ALTA FLORESTA", "ARAGUAIA", "CANARANA", "COLIDER", "COMODORO",
    "ITAPOA", "PALESTINA", "PIQUETE", "PONTES E LACERDA", "SAO GABRIEL"
]

# Mapeamento para nomes da planilha (VOCÊ PODE PERSONALIZAR!)
NOMES_PLANILHA = {
    "ALTA FLORESTA": "Alta Floresta",
    "ARAGUAIA": "Araguaia", 
    "CANARANA": "Canarana",
    "COLIDER": "Colíder",
    "COMODORO": "Comodoro",
    "ITAPOA": "Itapoã",
    "PALESTINA": "Palestina",
    "PIQUETE": "Piqueté",
    "PONTES E LACERDA": "Pontes e Lacerda",
    "SAO GABRIEL": "São Gabriel"
}

HIDRO_KEY = "HIDROFORTE"
COLUNA_TIPO_CAMPANHA = 'whatsapp categoria'
UNIDADES_FORA_DO_RATEIO = {"GESTAO SUL", "CENTRO SUL"}

# Mapeamento de aliases
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
    "GESTAO SUL": "GESTAO SUL",
    "CENTRO SUL": "CENTRO SUL",
    "HIDROFORTE": HIDRO_KEY,
    "HIDRO FORTE": HIDRO_KEY,
}

# ==================== FUNÇÕES AUXILIARES ====================
def normalizar_texto(texto) -> str:
    if pd.isna(texto):
        return ""
    texto_nfd = unicodedata.normalize('NFD', str(texto))
    texto_limpo = "".join(c for c in texto_nfd if unicodedata.category(c) != 'Mn')
    return " ".join(texto_limpo.upper().strip().split())

def identificar_unidade(texto, contexto: str) -> Optional[str]:
    t = normalizar_texto(texto)
    if not t:
        return None
    
    for chave in sorted(ALIASES.keys(), key=len, reverse=True):
        chave_norm = normalizar_texto(chave)
        if chave_norm and chave_norm in t:
            unidade = ALIASES[chave]
            if contexto != 'USUÁRIOS' and unidade in UNIDADES_FORA_DO_RATEIO:
                return None
            return unidade
    return None

def calcular_percentuais(contagem: pd.Series, unidades_validas: List[str]) -> Dict[str, float]:
    total_valido = sum(int(contagem.get(u, 0)) for u in unidades_validas)
    percentuais = {u: 0.0 for u in unidades_validas}
    
    if total_valido > 0:
        soma = 0.0
        for u in unidades_validas:
            qtd = int(contagem.get(u, 0))
            percentuais[u] = round((qtd / total_valido) * 100, 2)
            soma += percentuais[u]
        
        # Ajuste para garantir 100%
        if abs(soma - 100) > 0.01 and total_valido > 0:
            diferenca = round(100 - soma, 2)
            if percentuais:
                max_unidade = max(percentuais.items(), key=lambda x: (contagem.get(x[0], 0), x[1]))
                percentuais[max_unidade[0]] = round(percentuais[max_unidade[0]] + diferenca, 2)
    
    return percentuais

def processar_csv(caminho: str, coluna_unidade: str, nome_relatorio: str) -> Dict:
    """Processa um CSV e retorna dados estruturados"""
    try:
        df = pd.read_csv(caminho, encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
        
        df['unidade_match'] = df[coluna_unidade.lower()].apply(lambda x: identificar_unidade(x, nome_relatorio))
        contagem = df['unidade_match'].value_counts()
        
        percentuais = calcular_percentuais(contagem, UNIDADES_ALVO)
        
        resultado = {
            'dados': {},
            'hidroforte': int(contagem.get(HIDRO_KEY, 0)),
            'nao_mapeado': int(df['unidade_match'].isna().sum()),
            'total_valido': sum(int(contagem.get(u, 0)) for u in UNIDADES_ALVO)
        }
        
        # Adiciona unidades fora do rateio para usuários
        if nome_relatorio == 'USUÁRIOS':
            resultado['fora_rateio'] = {
                u: int(contagem.get(u, 0)) for u in UNIDADES_FORA_DO_RATEIO
            }
        
        for unidade in UNIDADES_ALVO:
            resultado['dados'][NOMES_PLANILHA.get(unidade, unidade)] = {
                'quantidade': int(contagem.get(unidade, 0)),
                'percentual': percentuais[unidade]
            }
        
        return resultado
        
    except Exception as e:
        return {'erro': str(e)}

# ==================== ENDPOINTS DA API ====================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'message': 'API de relatórios funcionando'})

@app.route('/processar', methods=['POST'])
def processar_arquivos():
    """Endpoint principal que recebe os CSVs e retorna relatório consolidado"""
    
    # Verifica se os arquivos foram enviados
    arquivos_necessarios = ['conversas', 'campanhas', 'presencial', 'usuarios']
    arquivos_enviados = {}
    
    for nome in arquivos_necessarios:
        if f'arquivo_{nome}' not in request.files:
            return jsonify({'erro': f'Arquivo {nome}.csv não enviado'}), 400
        arquivo = request.files[f'arquivo_{nome}']
        if arquivo.filename == '':
            return jsonify({'erro': f'Arquivo {nome}.csv vazio'}), 400
        
        # Salva temporariamente
        temp_dir = tempfile.gettempdir()
        caminho = os.path.join(temp_dir, secure_filename(arquivo.filename))
        arquivo.save(caminho)
        arquivos_enviados[nome] = caminho
    
    try:
        # Processa conversas
        df_conv = pd.read_csv(arquivos_enviados['conversas'], encoding='utf-8-sig')
        df_conv.columns = df_conv.columns.str.strip().str.lower()
        col_conv = 'app integration id' if 'app integration id' in df_conv.columns else 'unidade'
        dados_conversas = processar_csv(arquivos_enviados['conversas'], col_conv, 'CONVERSAS')
        
        # Processa campanhas
        df_camp = pd.read_csv(arquivos_enviados['campanhas'], encoding='utf-8-sig')
        df_camp.columns = df_camp.columns.str.strip().str.lower()
        
        # Filtra concluídos
        status_col = 'status da chave' if 'status da chave' in df_camp.columns else 'status'
        df_camp = df_camp[df_camp[status_col].apply(normalizar_texto) == 'CONCLUIDO']
        
        # Separa por tipo
        tipo_col = COLUNA_TIPO_CAMPANHA.lower() if COLUNA_TIPO_CAMPANHA.lower() in df_camp.columns else 'whatsapp categoria'
        if tipo_col in df_camp.columns:
            df_camp['categoria_norm'] = df_camp[tipo_col].apply(normalizar_texto)
            dep_col = 'departamento' if 'departamento' in df_camp.columns else 'unidade'
            
            marketing_df = df_camp[df_camp['categoria_norm'].str.contains('MARKETING', na=False)]
            utility_df = df_camp[df_camp['categoria_norm'].str.contains('UTILITY', na=False)]
            
            dados_marketing = processar_df(marketing_df, dep_col, 'CAMPANHAS_MARKETING')
            dados_utility = processar_df(utility_df, dep_col, 'CAMPANHAS_UTILITY')
        else:
            dados_marketing = {'erro': 'Coluna de categoria não encontrada'}
            dados_utility = {'erro': 'Coluna de categoria não encontrada'}
        
        # Processa presencial
        dados_presencial = processar_csv(arquivos_enviados['presencial'], 'empresa', 'PRESENCIAL')
        
        # Processa usuários
        dados_usuarios = processar_csv(arquivos_enviados['usuarios'], 'etiquetas', 'USUÁRIOS')
        
        # Monta relatório consolidado
        relatorio = {
            'conversas': dados_conversas,
            'campanhas_marketing': dados_marketing,
            'campanhas_utility': dados_utility,
            'presencial': dados_presencial,
            'usuarios': dados_usuarios
        }
        
        return jsonify(relatorio)
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500
    finally:
        # Limpa arquivos temporários
        for caminho in arquivos_enviados.values():
            if os.path.exists(caminho):
                os.remove(caminho)

def processar_df(df: pd.DataFrame, coluna: str, nome_relatorio: str) -> Dict:
    """Processa um DataFrame diretamente"""
    df = df.copy()
    df['unidade_match'] = df[coluna].apply(lambda x: identificar_unidade(x, nome_relatorio))
    contagem = df['unidade_match'].value_counts()
    
    percentuais = calcular_percentuais(contagem, UNIDADES_ALVO)
    
    resultado = {
        'dados': {},
        'hidroforte': int(contagem.get(HIDRO_KEY, 0)),
        'nao_mapeado': int(df['unidade_match'].isna().sum()),
        'total_valido': sum(int(contagem.get(u, 0)) for u in UNIDADES_ALVO)
    }
    
    for unidade in UNIDADES_ALVO:
        resultado['dados'][NOMES_PLANILHA.get(unidade, unidade)] = {
            'quantidade': int(contagem.get(unidade, 0)),
            'percentual': percentuais[unidade]
        }
    
    return resultado

@app.route('/exportar_excel', methods=['POST'])
def exportar_excel():
    """Gera um arquivo Excel pronto para alimentar planilhas"""
    
    # Primeiro processa os dados
    resposta = processar_arquivos()
    if isinstance(resposta, tuple):
        dados = resposta[0].get_json()
    else:
        dados = resposta.get_json()
    
    if 'erro' in dados:
        return jsonify(dados), 400
    
    # Cria um Excel com múltiplas abas
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        
        for nome_relatorio, dados_relatorio in dados.items():
            if 'erro' in dados_relatorio:
                continue
                
            # Converte para DataFrame
            linhas = []
            for unidade_nome, info in dados_relatorio.get('dados', {}).items():
                linhas.append({
                    'Unidade': unidade_nome,
                    'Quantidade': info['quantidade'],
                    'Percentual (%)': info['percentual']
                })
            
            df = pd.DataFrame(linhas)
            
            # Adiciona linha de totais
            total_qtd = sum(info['quantidade'] for info in dados_relatorio.get('dados', {}).values())
            df.loc[len(df)] = ['TOTAL', total_qtd, 100.0]
            
            # Adiciona informações extras
            notas = pd.DataFrame([
                ['HIDROFORTE', dados_relatorio.get('hidroforte', 0), '(Não incluído no percentual)'],
                ['Não mapeados', dados_relatorio.get('nao_mapeado', 0), '(Não identificados)'],
                ['Total válido', dados_relatorio.get('total_valido', 0), '(Base para percentuais)']
            ], columns=['Observação', 'Quantidade', 'Nota'])
            
            # Salva no Excel
            nome_aba = nome_relatorio.replace('_', ' ').title()
            df.to_excel(writer, sheet_name=nome_aba, index=False)
            notas.to_excel(writer, sheet_name=f'{nome_aba}_Notas', index=False)
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='relatorio_consolidado.xlsx'
    )

@app.route('/configurar_nomes', methods=['POST'])
def configurar_nomes():
    """Endpoint para personalizar os nomes das unidades na planilha"""
    global NOMES_PLANILHA
    
    novos_nomes = request.json.get('nomes', {})
    for unidade_interna, nome_exibicao in novos_nomes.items():
        if unidade_interna in NOMES_PLANILHA:
            NOMES_PLANILHA[unidade_interna] = nome_exibicao
    
    return jsonify({
        'mensagem': 'Nomes atualizados com sucesso',
        'nomes_atuais': NOMES_PLANILHA
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)