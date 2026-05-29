import pandas as pd
import unicodedata
import os
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

# ==================== CONFIGURAÇÕES ====================
UNIDADES_ALVO = [
    "ALTA FLORESTA", "ARAGUAIA", "CANARANA", "COLIDER", "COMODORO",
    "ITAPOA", "PALESTINA", "PIQUETE", "PONTES E LACERDA", "SAO GABRIEL"
]

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

def processar_arquivo(caminho, coluna_unidade, nome_relatorio):
    """Processa um arquivo CSV e retorna dados"""
    try:
        df = pd.read_csv(caminho, encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
        
        # Encontra a coluna correta
        coluna = None
        for col in df.columns:
            if coluna_unidade.lower() in col:
                coluna = col
                break
        
        if coluna is None:
            print(f"  ⚠️ Coluna '{coluna_unidade}' não encontrada em {nome_relatorio}")
            return None
        
        df['unidade_match'] = df[coluna].apply(identificar_unidade)
        contagem = df['unidade_match'].value_counts()
        
        total_valido = sum(int(contagem.get(u, 0)) for u in UNIDADES_ALVO)
        
        dados = []
        for unidade in UNIDADES_ALVO:
            qtd = int(contagem.get(unidade, 0))
            percentual = round((qtd / total_valido * 100), 2) if total_valido > 0 else 0
            dados.append({
                'Unidade': NOMES_PLANILHA.get(unidade, unidade),
                'Quantidade': qtd,
                'Percentual (%)': percentual
            })
        
        # Adiciona total
        dados.append({
            'Unidade': 'TOTAL',
            'Quantidade': total_valido,
            'Percentual (%)': round(sum(d['Percentual (%)'] for d in dados), 2)
        })
        
        return {
            'dados': dados,
            'hidroforte': int(contagem.get(HIDRO_KEY, 0)),
            'nao_mapeado': int(df['unidade_match'].isna().sum()),
            'total_valido': total_valido
        }
    except Exception as e:
        print(f"  ❌ Erro ao processar {nome_relatorio}: {e}")
        return None

def gerar_excel_completo():
    """Gera o arquivo Excel com todas as abas"""
    
    print("🚀 Iniciando geração do relatório...")
    print("=" * 50)
    
    # Verifica se os arquivos existem
    arquivos = {
        'Conversas': ('arquivos_entrada/conversas.csv', 'app integration id'),
        'Campanhas_Marketing': ('arquivos_entrada/campanhas.csv', 'departamento'),
        'Campanhas_Utility': ('arquivos_entrada/campanhas.csv', 'departamento'),
        'Presencial': ('arquivos_entrada/presencial.csv', 'empresa'),
        'Usuários': ('arquivos_entrada/usuarios.csv', 'etiquetas')
    }
    
    resultados = {}
    
    # Processa conversas
    if os.path.exists('arquivos_entrada/conversas.csv'):
        resultados['Conversas'] = processar_arquivo('arquivos_entrada/conversas.csv', 'app integration id', 'Conversas')
    else:
        print("❌ Arquivo conversas.csv não encontrado!")
    
    # Processa campanhas (filtra por status e tipo)
    if os.path.exists('arquivos_entrada/campanhas.csv'):
        try:
            df_camp = pd.read_csv('arquivos_entrada/campanhas.csv', encoding='utf-8-sig')
            df_camp.columns = df_camp.columns.str.strip().str.lower()
            
            # Filtra status concluído
            status_col = 'status da chave' if 'status da chave' in df_camp.columns else 'status'
            df_camp = df_camp[df_camp[status_col].apply(normalizar_texto) == 'CONCLUIDO']
            
            # Separa por categoria
            tipo_col = COLUNA_TIPO_CAMPANHA.lower()
            if tipo_col in df_camp.columns:
                df_camp['categoria_norm'] = df_camp[tipo_col].apply(normalizar_texto)
                dep_col = 'departamento' if 'departamento' in df_camp.columns else 'unidade'
                
                marketing_df = df_camp[df_camp['categoria_norm'].str.contains('MARKETING', na=False)]
                utility_df = df_camp[df_camp['categoria_norm'].str.contains('UTILITY', na=False)]
                
                # Processa marketing
                if not marketing_df.empty:
                    df_temp = marketing_df.copy()
                    df_temp['unidade_match'] = df_temp[dep_col].apply(identificar_unidade)
                    contagem = df_temp['unidade_match'].value_counts()
                    total_valido = sum(int(contagem.get(u, 0)) for u in UNIDADES_ALVO)
                    dados = []
                    for unidade in UNIDADES_ALVO:
                        qtd = int(contagem.get(unidade, 0))
                        percentual = round((qtd / total_valido * 100), 2) if total_valido > 0 else 0
                        dados.append({'Unidade': NOMES_PLANILHA.get(unidade, unidade), 'Quantidade': qtd, 'Percentual (%)': percentual})
                    dados.append({'Unidade': 'TOTAL', 'Quantidade': total_valido, 'Percentual (%)': round(sum(d['Percentual (%)'] for d in dados), 2)})
                    resultados['Campanhas_Marketing'] = {'dados': dados, 'hidroforte': int(contagem.get(HIDRO_KEY, 0)), 'nao_mapeado': int(df_temp['unidade_match'].isna().sum()), 'total_valido': total_valido}
                
                # Processa utility
                if not utility_df.empty:
                    df_temp = utility_df.copy()
                    df_temp['unidade_match'] = df_temp[dep_col].apply(identificar_unidade)
                    contagem = df_temp['unidade_match'].value_counts()
                    total_valido = sum(int(contagem.get(u, 0)) for u in UNIDADES_ALVO)
                    dados = []
                    for unidade in UNIDADES_ALVO:
                        qtd = int(contagem.get(unidade, 0))
                        percentual = round((qtd / total_valido * 100), 2) if total_valido > 0 else 0
                        dados.append({'Unidade': NOMES_PLANILHA.get(unidade, unidade), 'Quantidade': qtd, 'Percentual (%)': percentual})
                    dados.append({'Unidade': 'TOTAL', 'Quantidade': total_valido, 'Percentual (%)': round(sum(d['Percentual (%)'] for d in dados), 2)})
                    resultados['Campanhas_Utility'] = {'dados': dados, 'hidroforte': int(contagem.get(HIDRO_KEY, 0)), 'nao_mapeado': int(df_temp['unidade_match'].isna().sum()), 'total_valido': total_valido}
        except Exception as e:
            print(f"❌ Erro ao processar campanhas: {e}")
    
    # Processa presencial
    if os.path.exists('arquivos_entrada/presencial.csv'):
        resultados['Presencial'] = processar_arquivo('arquivos_entrada/presencial.csv', 'empresa', 'Presencial')
    
    # Processa usuários
    if os.path.exists('arquivos_entrada/usuarios.csv'):
        resultados['Usuários'] = processar_arquivo('arquivos_entrada/usuarios.csv', 'etiquetas', 'Usuários')
    
    # Gera Excel
    nome_arquivo = f'relatorio_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    with pd.ExcelWriter(nome_arquivo, engine='openpyxl') as writer:
        for nome_aba, dados in resultados.items():
            if dados and 'dados' in dados:
                df = pd.DataFrame(dados['dados'])
                df.to_excel(writer, sheet_name=nome_aba[:31], index=False)
                
                # Adiciona notas
                notas = pd.DataFrame([
                    ['HIDROFORTE', dados.get('hidroforte', 0), '(Não incluído no percentual)'],
                    ['Não mapeados', dados.get('nao_mapeado', 0), '(Não identificados)'],
                    ['Total válido', dados.get('total_valido', 0), '(Base para percentuais)']
                ], columns=['Observação', 'Quantidade', 'Nota'])
                notas.to_excel(writer, sheet_name=f'{nome_aba[:27]}_Notas', index=False)
    
    print("=" * 50)
    print(f"✅ RELATÓRIO GERADO COM SUCESSO!")
    print(f"📁 Arquivo: {nome_arquivo}")
    print(f"📂 Local: {os.path.abspath(nome_arquivo)}")
    return nome_arquivo

if __name__ == "__main__":
    gerar_excel_completo()