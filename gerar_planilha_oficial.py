import pandas as pd
import unicodedata
import os
from datetime import datetime

# ==================== CONFIGURAÇÕES ====================

# Mapeamento de unidades (nome interno -> nome na planilha)
UNIDADES_CONFIG = {
    "ALTA FLORESTA": {
        "nome_planilha": "Alta Floresta",
        "franquia": 1000  # Valor padrão, você pode ajustar
    },
    "ARAGUAIA": {
        "nome_planilha": "Araguaia",
        "franquia": 900
    },
    "CANARANA": {
        "nome_planilha": "Canarana",
        "franquia": 800
    },
    "COLIDER": {
        "nome_planilha": "Colíder",
        "franquia": 850
    },
    "COMODORO": {
        "nome_planilha": "Comodoro",
        "franquia": 750
    },
    "ITAPOA": {
        "nome_planilha": "Itapoã",
        "franquia": 950
    },
    "PALESTINA": {
        "nome_planilha": "Palestina",
        "franquia": 700
    },
    "PIQUETE": {
        "nome_planilha": "Piqueté",
        "franquia": 650
    },
    "PONTES E LACERDA": {
        "nome_planilha": "Pontes e Lacerda",
        "franquia": 1100
    },
    "SAO GABRIEL": {
        "nome_planilha": "São Gabriel",
        "franquia": 800
    }
}

# Mapeamento de aliases (como os nomes aparecem nos CSVs)
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

# ==================== FUNÇÕES AUXILIARES ====================

def normalizar_texto(texto):
    """Remove acentos e padroniza texto"""
    if pd.isna(texto):
        return ""
    texto_nfd = unicodedata.normalize('NFD', str(texto))
    texto_limpo = "".join(c for c in texto_nfd if unicodedata.category(c) != 'Mn')
    return " ".join(texto_limpo.upper().strip().split())

def identificar_unidade(texto):
    """Identifica a unidade a partir do texto"""
    t = normalizar_texto(texto)
    if not t:
        return None
    for chave in sorted(ALIASES.keys(), key=len, reverse=True):
        chave_norm = normalizar_texto(chave)
        if chave_norm and chave_norm in t:
            return ALIASES[chave]
    return None

def carregar_e_processar(caminho, coluna_alvo, colunas_para_normalizar=None):
    """Carrega CSV e normaliza as colunas especificadas"""
    if not os.path.exists(caminho):
        print(f"  ⚠️ Arquivo não encontrado: {caminho}")
        return None
    
    try:
        df = pd.read_csv(caminho, encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.lower()
        
        # Se tiver colunas para normalizar
        if colunas_para_normalizar:
            for col in colunas_para_normalizar:
                if col.lower() in df.columns:
                    df[col.lower()] = df[col.lower()].apply(normalizar_texto)
        
        # Identifica unidade na coluna alvo
        col_alvo = None
        for col in df.columns:
            if coluna_alvo.lower() in col:
                col_alvo = col
                break
        
        if col_alvo:
            df['unidade'] = df[col_alvo].apply(identificar_unidade)
            return df
        else:
            print(f"  ⚠️ Coluna '{coluna_alvo}' não encontrada em {caminho}")
            return None
            
    except Exception as e:
        print(f"  ❌ Erro ao carregar {caminho}: {e}")
        return None

def contar_por_unidade(df, filtro=None):
    """Conta registros por unidade"""
    if df is None:
        return {unidade: 0 for unidade in UNIDADES_CONFIG.keys()}
    
    df_filtrado = df.copy()
    if filtro:
        df_filtrado = df_filtrado[df_filtrado['unidade'].notna()]
        for col, valor in filtro.items():
            if col in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado[col] == valor]
    
    contagem = df_filtrado['unidade'].value_counts()
    
    resultado = {}
    for unidade in UNIDADES_CONFIG.keys():
        resultado[unidade] = int(contagem.get(unidade, 0))
    
    return resultado

# ==================== PROCESSAMENTO PRINCIPAL ====================

def gerar_planilha_completa():
    """Gera a planilha no formato oficial"""
    
    print("\n" + "="*60)
    print("📊 GERADOR DE PLANILHA OFICIAL - UNIDADES NORTE")
    print("="*60 + "\n")
    
    # Verifica pasta de entrada
    if not os.path.exists('arquivos_entrada'):
        os.makedirs('arquivos_entrada')
        print("📁 Pasta 'arquivos_entrada' criada!")
        print("⚠️ Coloque os arquivos CSV dentro desta pasta e execute novamente.\n")
        return
    
    # 1. Carregar Conversas (Mensagens Receptivas Excedentes)
    print("📄 1. Carregando conversas.csv...")
    df_conversas = carregar_e_processar(
        'arquivos_entrada/conversas.csv',
        coluna_alvo='unidade',
        colunas_para_normalizar=['unidade', 'app integration id']
    )
    
    # 2. Carregar Presencial
    print("📄 2. Carregando presencial.csv...")
    df_presencial = carregar_e_processar(
        'arquivos_entrada/presencial.csv',
        coluna_alvo='empresa',
        colunas_para_normalizar=['empresa', 'status']
    )
    # Filtra apenas concluídos
    if df_presencial is not None and 'status' in df_presencial.columns:
        df_presencial = df_presencial[df_presencial['status'] == 'CONCLUIDO']
    
    # 3. Carregar Campanhas (Whatsapp Utility)
    print("📄 3. Carregando campanhas.csv...")
    df_campanhas = carregar_e_processar(
        'arquivos_entrada/campanhas.csv',
        coluna_alvo='departamento',
        colunas_para_normalizar=['departamento', 'status da chave', 'whatsapp categoria']
    )
    
    # Filtra apenas concluídos e Utility
    utility_count = {}
    if df_campanhas is not None:
        # Filtra status concluído
        if 'status da chave' in df_campanhas.columns:
            df_campanhas = df_campanhas[df_campanhas['status da chave'] == 'CONCLUIDO']
        
        # Filtra categoria UTILITY
        if 'whatsapp categoria' in df_campanhas.columns:
            df_utility = df_campanhas[df_campanhas['whatsapp categoria'].str.contains('UTILITY', na=False)]
            utility_count = contar_por_unidade(df_utility)
        else:
            utility_count = contar_por_unidade(df_campanhas)
    
    # 4. Carregar Usuários (Número oficial WhatsApp)
    print("📄 4. Carregando usuarios.csv...")
    df_usuarios = carregar_e_processar(
        'arquivos_entrada/usuarios.csv',
        coluna_alvo='etiquetas',
        colunas_para_normalizar=['etiquetas', 'situacao', 'situação']
    )
    # Filtra apenas ativos
    if df_usuarios is not None:
        col_situacao = None
        for col in ['situacao', 'situação']:
            if col in df_usuarios.columns:
                col_situacao = col
                break
        if col_situacao:
            df_usuarios = df_usuarios[df_usuarios[col_situacao] == 'ATIVO']
    
    # ==================== MONTAR PLANILHA ====================
    
    print("\n" + "="*60)
    print("🔧 Montando planilha final...")
    print("="*60 + "\n")
    
    # Contar cada métrica
    conversas_count = contar_por_unidade(df_conversas)
    presencial_count = contar_por_unidade(df_presencial)
    usuarios_count = contar_por_unidade(df_usuarios)
    
    # Criar lista de dados
    dados_planilha = []
    
    for unidade_interna, config in UNIDADES_CONFIG.items():
        # Calcular excedente (conversas - franquia)
        conversas = conversas_count.get(unidade_interna, 0)
        franquia = config['franquia']
        excedente = max(0, conversas - franquia)  # Só positivo se ultrapassar
        
        dados_planilha.append({
            'Unidade': config['nome_planilha'],
            'Franquia': franquia,
            'Mensagens Receptivas Excedentes': excedente,
            'Atendimento presencial': presencial_count.get(unidade_interna, 0),
            'Whatsapp utility': utility_count.get(unidade_interna, 0),
            'numero oficial whatsapp (waba)': usuarios_count.get(unidade_interna, 0)
        })
    
    # Criar DataFrame
    df_final = pd.DataFrame(dados_planilha)
    
    # Adicionar linha de total
    total_row = {
        'Unidade': 'TOTAL',
        'Franquia': df_final['Franquia'].sum(),
        'Mensagens Receptivas Excedentes': df_final['Mensagens Receptivas Excedentes'].sum(),
        'Atendimento presencial': df_final['Atendimento presencial'].sum(),
        'Whatsapp utility': df_final['Whatsapp utility'].sum(),
        'numero oficial whatsapp (waba)': df_final['numero oficial whatsapp (waba)'].sum()
    }
    df_final = pd.concat([df_final, pd.DataFrame([total_row])], ignore_index=True)
    
    # ==================== SALVAR ARQUIVO ====================
    
    nome_arquivo = f'planilha_unidades_norte_{datetime.now().strftime("%Y%m%d")}.xlsx'
    
    with pd.ExcelWriter(nome_arquivo, engine='openpyxl') as writer:
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
    
    print("✅ PLANILHA GERADA COM SUCESSO!")
    print(f"📁 Arquivo: {nome_arquivo}")
    print(f"📂 Local: {os.path.abspath(nome_arquivo)}")
    
    # Mostrar preview
    print("\n" + "="*60)
    print("📊 PREVIEW DA PLANILHA:")
    print("="*60)
    print(df_final.to_string(index=False))
    print("="*60)
    
    return nome_arquivo

# ==================== FUNÇÃO PARA ATUALIZAR FRANQUIAS ====================

def atualizar_franquias():
    """Permite atualizar os valores das franquias via arquivo CSV"""
    franquias_file = 'franquias.csv'
    
    if os.path.exists(franquias_file):
        df_franquias = pd.read_csv(franquias_file, encoding='utf-8-sig')
        for _, row in df_franquias.iterrows():
            unidade = row.get('unidade', '').upper()
            nova_franquia = row.get('franquia', 0)
            if unidade in UNIDADES_CONFIG:
                UNIDADES_CONFIG[unidade]['franquia'] = int(nova_franquia)
        print("✅ Franquias atualizadas pelo arquivo franquias.csv")
    else:
        # Criar arquivo exemplo
        df_exemplo = pd.DataFrame([
            {'unidade': 'ALTA FLORESTA', 'franquia': 1000},
            {'unidade': 'ARAGUAIA', 'franquia': 900},
            {'unidade': 'CANARANA', 'franquia': 800},
            {'unidade': 'COLIDER', 'franquia': 850},
            {'unidade': 'COMODORO', 'franquia': 750},
            {'unidade': 'ITAPOA', 'franquia': 950},
            {'unidade': 'PALESTINA', 'franquia': 700},
            {'unidade': 'PIQUETE', 'franquia': 650},
            {'unidade': 'PONTES E LACERDA', 'franquia': 1100},
            {'unidade': 'SAO GABRIEL', 'franquia': 800}
        ])
        df_exemplo.to_csv('franquias.csv', index=False, encoding='utf-8-sig')
        print("📝 Arquivo 'franquias.csv' criado! Edite os valores das franquias conforme necessário.")

# ==================== EXECUÇÃO ====================

if __name__ == "__main__":
    # Atualiza franquias se existir arquivo
    atualizar_franquias()
    
    # Gera a planilha
    gerar_planilha_completa()
    
    print("\n✨ Processo concluído! Verifique o arquivo Excel gerado.")