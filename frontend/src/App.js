import React, { useEffect } from 'react';
import { Layout, Typography, Alert } from 'antd';
import { useAtom } from 'jotai';
import { useSearchParams } from 'react-router-dom';
import StockDashboard from './components/StockDashboard';
import { 
  stockCodeAtom, 
  errorAtom
} from './store/atoms';

const { Header, Content } = Layout;
const { Title } = Typography;

function App() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [stockCode, setStockCode] = useAtom(stockCodeAtom);
  const [error, setError] = useAtom(errorAtom);

  // 从URL获取股票代码（只负责同步，不获取数据）
  useEffect(() => {
    const codeFromUrl = searchParams.get('code');
    if (codeFromUrl && codeFromUrl !== stockCode) {
      setStockCode(codeFromUrl);
    } else if (!codeFromUrl) {
      // 如果URL没有code参数，使用默认的000001
      setSearchParams({ code: stockCode });
    }
  }, [searchParams, stockCode, setStockCode, setSearchParams]);

  // 当股票代码改变时更新URL（数据获取由StockDashboard处理）
  const handleStockCodeChange = (newCode) => {
    setStockCode(newCode);
    setSearchParams({ code: newCode });
  };

  return (
    <Layout className="layout" style={{ minHeight: '100vh' }}>
      {/* <Header style={{ 
        display: 'flex', 
        alignItems: 'center', 
        background: '#fff', 
        borderBottom: '1px solid #f0f0f0'
      }}>
        <Title level={2} style={{ 
          margin: 0, 
          color: '#1890ff',
          fontWeight: 'bold'
        }}>
          📈 股票大单数据分析
        </Title>
      </Header>
       */}
      <Content style={{ padding: '24px 50px' }}>
        {error && (
          <Alert
            message="错误"
            description={error}
            type="error"
            showIcon
            closable
            onClose={() => setError(null)}
            style={{ marginBottom: 16 }}
          />
        )}
        
        <StockDashboard onStockCodeChange={handleStockCodeChange} />
      </Content>
      
      {/* <Footer style={{ textAlign: 'center', background: '#f0f2f5' }}>
        <div style={{ color: '#666' }}>
          股票大单数据分析 ©2024 Created by NiuNiuNiu
        </div>
        <div style={{ color: '#999', fontSize: '12px', marginTop: '4px' }}>
          数据仅供参考，不构成投资建议
        </div>
      </Footer> */}
    </Layout>
  );
}

export default App; 