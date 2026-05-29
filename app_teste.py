from flask import Flask, render_template_string, request, jsonify, send_file
import pandas as pd
import unicodedata
import io
import base64
import os
from datetime import datetime

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configuração simples das unidades
UNIDADES = [
    "ALTA FLORESTA", "ARAGUAIA", "CANARANA", "COLIDER", "COMODORO",
    "ITAPOA", "PALESTINA", "PIQUETE", "PONTES E LACERDA", "SAO GABRIEL"
]

def normalizar(texto):
    if pd.isna(texto):
        return ""
    return str(texto).upper().strip()

def identificar_unidade(texto):
    t = normalizar(texto)
    for unidade in UNIDADES:
        if unidade in t:
            return unidade
    return None

HTML_SIMPLES = '''
<!DOCTYPE html>
<html>
<head>
    <title>Teste Rateio</title>
    <style>
        body { font-family: Arial; padding: 20px; }
        .upload-area { border: 2px dashed #ccc; padding: 20px; margin: 10px 0; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; cursor: pointer; }
        .status { margin-top: 20px; padding: 10px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>📊 Teste Rateio Norte Saneamento</h1>
    
    <div class="upload-area">
        <h3>📄 Conversas</h3>
        <input type="file" id="conversas" accept=".csv">
    </div>
    
    <div class="upload-area">
        <h3>👥 Usuários</h3>
        <input type="file" id="usuarios" accept=".csv">
    </div>
    
    <div class="upload-area">
        <h3>🏢 Presencial</h3>
        <input type="file" id="presencial" accept=".csv">
    </div>
    
    <div class="upload-area">
        <h3>📢 Campanhas</h3>
        <input type="file" id="campanhas" accept=".csv">
    </div>
    
    <button onclick="processar()">🚀 Gerar Rateio</button>
    <div id="status"></div>
    
    <script>
        async function processar() {
            const formData = new FormData();
            const files = ['conversas', 'usuarios', 'presencial', 'campanhas'];
            
            for (const fileId of files) {
                const input = document.getElementById(fileId);
                if (input.files.length > 0) {
                    formData.append(fileId, input.files[0]);
                }
            }
            
            const statusDiv = document.getElementById('status');
            statusDiv.innerHTML = '<div class="status">⏳ Processando...</div>';
            
            try {
                const response = await fetch('/teste', { method: 'POST', body: formData });
                const data = await response.json();
                
                if (data.success) {
                    statusDiv.innerHTML = '<div class="status success">✅ ' + data.mensagem + '</div>';
                    if (data.excel) {
                        const link = document.createElement('a');
                        link.href = 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,' + data.excel;
                        link.download = 'teste_rateio.xlsx';
                        link.click();
                    }
                } else {
                    statusDiv.innerHTML = '<div class="status error">❌ ' + data.erro + '</div>';
                }
            } catch (error) {
                statusDiv.innerHTML = '<div class="status error">❌ Erro: ' + error.message + '</div>';
            }
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return HTML_SIMPLES

@app.route('/teste', methods=['POST'])
def teste():
    resultados = {}
    
    # Processar Conversas
    if 'conversas' in request.files and request.files['conversas'].filename:
        arquivo = request.files['conversas']
        caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'conversas.csv')
        arquivo.save(caminho)
        
        try:
            df = pd.read_csv(caminho, encoding='utf-8-sig')
            print(f"\n📄 CONVERSAS:")
            print(f"   Colunas: {list(df.columns)}")
            print(f"   Primeiras linhas:\n{df.head()}")
            
            # Procurar coluna com unidade
            coluna_unidade = None
            for col in df.columns:
                if 'unidade' in col.lower() or 'empresa' in col.lower() or 'app' in col.lower():
                    coluna_unidade = col
                    break
            
            if coluna_unidade:
                df['unidade_identificada'] = df[coluna_unidade].apply(identificar_unidade)
                contagem = df['unidade_identificada'].value_counts()
                resultados['conversas'] = {u: int(contagem.get(u, 0)) for u in UNIDADES}
                print(f"   Contagem: {resultados['conversas']}")
            else:
                print(f"   ❌ Nenhuma coluna de unidade encontrada!")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
        finally:
            os.remove(caminho)
    
    # Processar Usuários
    if 'usuarios' in request.files and request.files['usuarios'].filename:
        arquivo = request.files['usuarios']
        caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'usuarios.csv')
        arquivo.save(caminho)
        
        try:
            df = pd.read_csv(caminho, encoding='utf-8-sig')
            print(f"\n📄 USUÁRIOS:")
            print(f"   Colunas: {list(df.columns)}")
            print(f"   Primeiras linhas:\n{df.head()}")
            
            coluna_etiqueta = None
            for col in df.columns:
                if 'etiqueta' in col.lower() or 'unidade' in col.lower():
                    coluna_etiqueta = col
                    break
            
            if coluna_etiqueta:
                df['unidade_identificada'] = df[coluna_etiqueta].apply(identificar_unidade)
                contagem = df['unidade_identificada'].value_counts()
                resultados['usuarios'] = {u: int(contagem.get(u, 0)) for u in UNIDADES}
                print(f"   Contagem: {resultados['usuarios']}")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
        finally:
            os.remove(caminho)
    
    # Se conseguiu processar algo, gera Excel
    if resultados:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for nome, dados in resultados.items():
                df_res = pd.DataFrame([dados], index=UNIDADES).T
                df_res.columns = [nome]
                df_res.to_excel(writer, sheet_name=nome)
        
        output.seek(0)
        excel_base64 = base64.b64encode(output.getvalue()).decode('utf-8')
        
        return jsonify({
            'success': True,
            'excel': excel_base64,
            'mensagem': f'Processado: {", ".join(resultados.keys())}'
        })
    else:
        return jsonify({
            'success': False,
            'erro': 'Nenhum arquivo processado. Verifique se os CSVs têm as colunas corretas.'
        })

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 SERVIDOR DE TESTE")
    print("📱 Acesse: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)