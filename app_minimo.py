from flask import Flask, request, jsonify, send_file
import pandas as pd
import io
import base64
import os

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# HTML simples embutido
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Rateio Norte</title>
    <style>
        body { font-family: Arial; padding: 20px; }
        .card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; cursor: pointer; font-size: 16px; }
        #status { margin-top: 20px; padding: 10px; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>📊 Rateio Norte Saneamento</h1>
    
    <div class="card">
        <h3>📄 Conversas</h3>
        <input type="file" id="conversas" accept=".csv">
    </div>
    
    <div class="card">
        <h3>👥 Usuários</h3>
        <input type="file" id="usuarios" accept=".csv">
    </div>
    
    <div class="card">
        <h3>🏢 Presencial</h3>
        <input type="file" id="presencial" accept=".csv">
    </div>
    
    <div class="card">
        <h3>📢 Campanhas</h3>
        <input type="file" id="campanhas" accept=".csv">
    </div>
    
    <button onclick="enviar()">🚀 Gerar Rateio</button>
    <div id="status"></div>
    
    <script>
        async function enviar() {
            const formData = new FormData();
            
            const conversas = document.getElementById('conversas').files[0];
            const usuarios = document.getElementById('usuarios').files[0];
            const presencial = document.getElementById('presencial').files[0];
            const campanhas = document.getElementById('campanhas').files[0];
            
            if (conversas) formData.append('conversas', conversas);
            if (usuarios) formData.append('usuarios', usuarios);
            if (presencial) formData.append('presencial', presencial);
            if (campanhas) formData.append('campanhas', campanhas);
            
            const statusDiv = document.getElementById('status');
            statusDiv.innerHTML = '<div class="status">⏳ Processando...</div>';
            
            try {
                const response = await fetch('/processar', {
                    method: 'POST',
                    body: formData
                });
                
                const text = await response.text();
                console.log('Resposta:', text);
                
                try {
                    const data = JSON.parse(text);
                    if (data.success) {
                        statusDiv.innerHTML = '<div class="status success">✅ ' + data.mensagem + '</div>';
                        if (data.excel) {
                            const link = document.createElement('a');
                            link.href = 'data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,' + data.excel;
                            link.download = 'rateio_norte.xlsx';
                            link.click();
                        }
                    } else {
                        statusDiv.innerHTML = '<div class="status error">❌ ' + data.erro + '</div>';
                    }
                } catch(e) {
                    statusDiv.innerHTML = '<div class="status error">❌ Erro: Resposta do servidor inválida. Verifique o console do servidor.</div>';
                }
            } catch(error) {
                statusDiv.innerHTML = '<div class="status error">❌ Erro: ' + error.message + '</div>';
            }
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return HTML

@app.route('/processar', methods=['POST'])
def processar():
    print("\n" + "="*50)
    print("🔍 PROCESSANDO ARQUIVOS")
    print("="*50)
    
    resultado = {}
    
    # Verificar se recebeu arquivos
    print(f"Arquivos recebidos: {list(request.files.keys())}")
    
    # Processa cada arquivo
    for nome_arquivo in ['conversas', 'usuarios', 'presencial', 'campanhas']:
        if nome_arquivo in request.files:
            arquivo = request.files[nome_arquivo]
            if arquivo.filename:
                print(f"\n📄 {nome_arquivo.upper()}: {arquivo.filename}")
                
                # Salvar temporariamente
                caminho = os.path.join(UPLOAD_FOLDER, arquivo.filename)
                arquivo.save(caminho)
                
                try:
                    df = pd.read_csv(caminho, encoding='utf-8-sig')
                    print(f"   Linhas: {len(df)}")
                    print(f"   Colunas: {list(df.columns)}")
                    resultado[nome_arquivo] = {
                        'linhas': len(df),
                        'colunas': list(df.columns)
                    }
                except Exception as e:
                    print(f"   ❌ Erro: {e}")
                    resultado[nome_arquivo] = {'erro': str(e)}
                finally:
                    os.remove(caminho)
    
    # Gerar resposta
    if resultado:
        # Criar Excel simples para teste
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for nome, info in resultado.items():
                if 'erro' in info:
                    df = pd.DataFrame([{'Status': 'Erro', 'Detalhe': info['erro']}])
                else:
                    df = pd.DataFrame([{
                        'Arquivo': nome,
                        'Linhas': info['linhas'],
                        'Colunas': ', '.join(info['colunas'])
                    }])
                df.to_excel(writer, sheet_name=nome[:31], index=False)
        
        output.seek(0)
        excel_base64 = base64.b64encode(output.getvalue()).decode('utf-8')
        
        return jsonify({
            'success': True,
            'excel': excel_base64,
            'mensagem': f'Processado: {len(resultado)} arquivo(s)'
        })
    else:
        return jsonify({
            'success': False,
            'erro': 'Nenhum arquivo enviado'
        })

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 SERVIDOR MINIMO - Rateio Norte")
    print("📱 Acesse: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)