import pandas as pd
import ofxparse
from io import BytesIO
import re
from datetime import datetime

def ler_ofx(arquivo_ofx):
    """Lê um arquivo OFX e retorna as transações em formato padronizado."""
    try:
        # Tentar ler o arquivo com diferentes codificações
        try:
            # Primeiro, tentar ler o arquivo como bytes
            arquivo_ofx.seek(0)
            conteudo = arquivo_ofx.read()
            
            # Tentar diferentes codificações
            for encoding in ['cp1252', 'latin1', 'utf-8', 'iso-8859-1']:
                try:
                    # Decodificar o conteúdo com a codificação atual
                    decoded_content = conteudo.decode(encoding, errors='replace')
                    
                    # Se chegou aqui, a decodificação funcionou
                    # Converter de volta para bytes para o ofxparse
                    ofx_bytes = BytesIO(decoded_content.encode('ascii', 'replace'))
                    ofx = ofxparse.OfxParser.parse(ofx_bytes)
                    
                    # Se chegou aqui sem erros, encontramos a codificação correta
                    break
                except Exception:
                    # Se falhar, tentar a próxima codificação
                    continue
            else:
                # Se todas as codificações falharem, tentar diretamente com os bytes originais
                ofx_bytes = BytesIO(conteudo)
                ofx = ofxparse.OfxParser.parse(ofx_bytes)
        except Exception as e:
            # Se ainda falhar, tentar uma abordagem alternativa
            arquivo_ofx.seek(0)
            ofx_bytes = BytesIO(arquivo_ofx.read())
            ofx = ofxparse.OfxParser.parse(ofx_bytes)
        
        transacoes = []
        for transacao in ofx.account.statement.transactions:
            # Tratar possíveis problemas de codificação na descrição
            descricao = ""
            if hasattr(transacao, 'memo') and transacao.memo:
                descricao = transacao.memo
            elif hasattr(transacao, 'payee') and transacao.payee:
                descricao = transacao.payee
                
            # Garantir que a descrição seja uma string válida
            if not isinstance(descricao, str):
                descricao = str(descricao)
            
            transacoes.append({
                'data': transacao.date,
                'valor': float(transacao.amount),
                'descricao': descricao
            })
        
        return transacoes
    except Exception as e:
        raise Exception(f"Erro ao processar arquivo OFX: {str(e)}")

def carregar_relatorio_dataframe(arquivo, nome_arquivo):
    """Carrega um arquivo CSV/Excel em um DataFrame pandas."""
    if nome_arquivo.endswith('.csv'):
        # Tentar diferentes encodings e delimitadores
        encodings = ['cp1252', 'utf-8', 'latin1', 'iso-8859-1']
        delimiters = [',', ';', '\t', '|']
        
        # Primeiro, tentar ler algumas linhas para análise
        try:
            # Resetar o ponteiro do arquivo para o início
            arquivo.seek(0)
            sample_data = arquivo.read(2048)  # Ler uma amostra para detecção
            arquivo.seek(0)  # Resetar novamente
            
            # Tentar detectar o delimitador analisando a amostra
            sample_str = sample_data.decode('utf-8', errors='ignore')
            delimiter_counts = {d: sample_str.count(d) for d in delimiters}
            
            # Ordenar delimitadores por frequência (mais frequente primeiro)
            sorted_delimiters = sorted(delimiters, key=lambda d: delimiter_counts[d], reverse=True)
        except Exception:
            sorted_delimiters = delimiters
        
        # Tentar cada combinação de encoding e delimitador
        for encoding in encodings:
            for delimiter in sorted_delimiters:
                try:
                    # Resetar o ponteiro do arquivo para o início
                    arquivo.seek(0)
                    
                    # Tentar com diferentes configurações
                    df = pd.read_csv(
                        arquivo, 
                        encoding=encoding, 
                        sep=delimiter, 
                        engine='python',
                        on_bad_lines='skip',  # Updated from error_bad_lines
                        low_memory=False        # Melhor para arquivos complexos
                    )
                    
                    # Verificar se o arquivo foi lido corretamente
                    if len(df.columns) > 1:
                        return df
                except Exception:
                    continue
        
        # Se nenhuma combinação funcionou, tentar métodos alternativos
        try:
            # Resetar o ponteiro do arquivo
            arquivo.seek(0)
            
            # Tentar com o pandas para detectar automaticamente
            df = pd.read_csv(
                arquivo, 
                encoding='utf-8', 
                sep=None,  # Tentar detectar automaticamente
                engine='python',
                on_bad_lines='skip',  # Updated from error_bad_lines
                low_memory=False
            )
            return df
        except Exception:
            pass
        
        # Tentar com o método de leitura de texto e processamento manual
        try:
            # Resetar o ponteiro do arquivo
            arquivo.seek(0)
            
            # Ler como texto e processar manualmente
            content = arquivo.read().decode('utf-8', errors='ignore')
            lines = content.splitlines()
            
            if not lines:
                raise Exception("Arquivo vazio")
            
            # Detectar delimitador na primeira linha
            first_line = lines[0]
            best_delimiter = max(delimiters, key=lambda d: first_line.count(d))
            
            # Criar DataFrame a partir das linhas divididas
            rows = [line.split(best_delimiter) for line in lines]
            
            # Garantir que todas as linhas tenham o mesmo número de colunas
            max_cols = max(len(row) for row in rows)
            padded_rows = [row + [''] * (max_cols - len(row)) for row in rows]
            
            # Criar DataFrame
            df = pd.DataFrame(padded_rows[1:], columns=padded_rows[0])
            return df
        except Exception as e:
            raise Exception(f"Não foi possível ler o arquivo CSV: {str(e)}")
    else:
        try:
            df = pd.read_excel(arquivo)
            return df
        except Exception as e:
            raise Exception(f"Não foi possível ler o arquivo Excel: {str(e)}")

def parse_date(date_str):
    """
    Tenta converter uma string de data em um objeto datetime usando vários formatos comuns.
    """
    if pd.isna(date_str) or date_str == '':
        return None
    
    # Se já for um objeto datetime, retornar diretamente
    if isinstance(date_str, datetime):
        return date_str
    
    # Converter para string se não for
    date_str = str(date_str).strip()
    
    # Remover horas se presentes
    date_str = date_str.split(' ')[0]
    
    # Lista de formatos comuns de data
    date_formats = [
        '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', 
        '%d.%m.%Y', '%Y.%m.%d', '%d-%b-%Y', '%d/%b/%Y',
        '%d/%m/%y', '%y-%m-%d', '%m/%d/%y', '%d.%m.%y'
    ]
    
    # Tentar cada formato
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Se nenhum formato funcionar, tentar extrair números da string
    try:
        # Extrair números da string (dia, mês, ano)
        numbers = re.findall(r'\d+', date_str)
        if len(numbers) >= 3:
            day, month, year = int(numbers[0]), int(numbers[1]), int(numbers[2])
            
            # Ajustar ano se necessário (assumir século 21 para anos de 2 dígitos)
            if year < 100:
                year += 2000 if year < 50 else 1900
                
            # Verificar se os valores são válidos para uma data
            if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
                return datetime(year, month, day)
    except Exception:
        pass
    
    # Se tudo falhar, retornar None
    return None

def converter_dataframe(df, mapeamento, tipo_relatorio, filtro_conta=None, debug=False):
    """Converte um DataFrame para o formato padronizado de transações."""
    transacoes = []
    problematic_dates = []
    
    # Verificar se o DataFrame não está vazio
    if df.empty:
        print("DataFrame vazio - nenhum dado para processar")
        return transacoes
        
    # Verificar se as colunas mapeadas existem no DataFrame
    colunas_necessarias = ['data', 'descricao']
    if tipo_relatorio == "Única coluna com Natureza (C/D)":
        colunas_necessarias.extend(['valor', 'natureza'])
    else:
        colunas_necessarias.extend(['receita', 'despesa'])
    
    # Adicionar 'conta' se estiver no mapeamento
    if 'conta' in mapeamento and mapeamento['conta']:
        colunas_necessarias.append('conta')
    
    # Verificar se todas as colunas necessárias estão no mapeamento e no DataFrame
    for coluna in colunas_necessarias:
        if coluna not in mapeamento or not mapeamento[coluna]:
            print(f"Aviso: Coluna '{coluna}' não está mapeada")
            continue
        if mapeamento[coluna] not in df.columns:
            print(f"Aviso: Coluna mapeada '{mapeamento[coluna]}' não existe no DataFrame")
            print(f"Colunas disponíveis: {', '.join(df.columns)}")
            continue
    
    # Aplicar filtro de conta, se fornecido
    if filtro_conta and mapeamento['conta'] and mapeamento['conta'] in df.columns:
        df = df[df[mapeamento['conta']] == filtro_conta]
    
    # Processar cada linha do DataFrame
    for idx, row in df.iterrows():
        # Processar data com tratamento robusto
        if 'data' not in mapeamento or not mapeamento['data'] or mapeamento['data'] not in df.columns:
            if debug:
                print(f"Pulando linha {idx}: coluna de data não encontrada")
            continue
            
        data_str = row[mapeamento['data']]
        data = parse_date(data_str)
        
        if data is None:
            if debug:
                problematic_dates.append((idx, data_str))
            continue  # Pular linhas com datas inválidas
        
        # Inicializar valores
        valor = 0
        receita = 0
        despesa = 0
        
        if tipo_relatorio == "Única coluna com Natureza (C/D)":
            # Verificar se as colunas necessárias existem
            if not mapeamento['valor'] or not mapeamento['natureza'] or \
               mapeamento['valor'] not in df.columns or mapeamento['natureza'] not in df.columns:
                if debug:
                    print(f"Pulando linha {idx}: colunas de valor ou natureza não encontradas")
                continue
                
            valor_str = row[mapeamento['valor']]
            natureza_str = str(row[mapeamento['natureza']]).strip().upper()
            
            # Converter valor para float, tratando diferentes formatos
            if pd.isna(valor_str):
                continue  # Pular se o valor for NaN
                
            if isinstance(valor_str, str):
                # Remover caracteres não numéricos, exceto ponto, vírgula e sinais
                valor_str = re.sub(r'[^\d.,+-]', '', valor_str)
                # Substituir vírgula por ponto para conversão
                valor_str = valor_str.replace('.', '').replace(',', '.').strip()
                try:
                    valor = float(valor_str) if valor_str else 0
                except ValueError:
                    # Tentar extrair números da string
                    match = re.search(r'[-+]?\d*[.,]?\d+', valor_str)
                    if match:
                        valor = float(match.group().replace(',', '.'))
                    else:
                        continue  # Pular se não conseguir converter
            else:
                try:
                    valor = float(valor_str)
                except (ValueError, TypeError):
                    continue  # Pular se não conseguir converter
            
            # Ajustar sinal conforme natureza (D=débito, C=crédito)
            # Verificar várias possibilidades de indicação de natureza
            if natureza_str in ['D', 'DEBITO', 'DÉBITO', 'DEBIT', 'SAIDA', 'SAÍDA', '-']:
                valor = -abs(valor)
            elif natureza_str in ['C', 'CREDITO', 'CRÉDITO', 'CREDIT', 'ENTRADA', '+']:
                valor = abs(valor)
            # Se não for possível determinar a natureza, usar o sinal do valor
            
            receita = valor if valor > 0 else 0
            despesa = abs(valor) if valor < 0 else 0
        else:
            # Relatório com colunas separadas para receita e despesa
            # Processar coluna de receita (entradas - valores positivos)
            if mapeamento['receita'] and mapeamento['receita'] in df.columns:
                receita_val = row[mapeamento['receita']]
                if pd.notna(receita_val) and receita_val != '':
                    if isinstance(receita_val, str):
                        # Limpar a string para conversão
                        receita_val = re.sub(r'[^\d.,+-]', '', str(receita_val))
                        receita_val = receita_val.replace('.', '').replace(',', '.').strip()
                        try:
                            receita = float(receita_val) if receita_val else 0
                        except ValueError:
                            match = re.search(r'[-+]?\d*[.,]?\d+', receita_val)
                            if match:
                                receita = float(match.group().replace(',', '.'))
                            else:
                                receita = 0
                    else:
                        try:
                            receita = float(receita_val) if pd.notna(receita_val) else 0
                        except (ValueError, TypeError):
                            receita = 0
                
                # Garantir que receita seja positiva
                receita = abs(receita)
            
            # Processar coluna de despesa (saídas - valores negativos)
            if mapeamento['despesa'] and mapeamento['despesa'] in df.columns:
                despesa_val = row[mapeamento['despesa']]
                if pd.notna(despesa_val) and despesa_val != '':
                    if isinstance(despesa_val, str):
                        # Limpar a string para conversão
                        despesa_val = re.sub(r'[^\d.,+-]', '', str(despesa_val))
                        despesa_val = despesa_val.replace('.', '').replace(',', '.').strip()
                        try:
                            despesa = float(despesa_val) if despesa_val else 0
                        except ValueError:
                            match = re.search(r'[-+]?\d*[.,]?\d+', despesa_val)
                            if match:
                                despesa = float(match.group().replace(',', '.'))
                            else:
                                despesa = 0
                    else:
                        try:
                            despesa = float(despesa_val) if pd.notna(despesa_val) else 0
                        except (ValueError, TypeError):
                            despesa = 0
                
                # Garantir que despesa seja positiva para armazenamento
                despesa = abs(despesa)
            
            # Calcular o valor líquido (receita - despesa)
            valor = receita - despesa
        
        # Obter descrição e conta
        descricao = str(row[mapeamento['descricao']]) if 'descricao' in mapeamento and mapeamento['descricao'] in df.columns and pd.notna(row[mapeamento['descricao']]) else ''
        conta = str(row[mapeamento['conta']]) if 'conta' in mapeamento and mapeamento['conta'] in df.columns and pd.notna(row[mapeamento['conta']]) else ''
        
        # Adicionar transação ao resultado
        transacoes.append({
            'data': data,
            'valor': valor,
            'descricao': descricao,
            'conta': conta,
            'receita': receita,
            'despesa': despesa
        })
    
    if debug and problematic_dates:
        print(f"Encontradas {len(problematic_dates)} datas problemáticas:")
        for idx, date_str in problematic_dates[:10]:  # Mostrar apenas as 10 primeiras para não sobrecarregar
            print(f"  Linha {idx}: '{date_str}'")
    
    if debug:
        print(f"Total de transações processadas: {len(transacoes)}")
    
    return transacoes
