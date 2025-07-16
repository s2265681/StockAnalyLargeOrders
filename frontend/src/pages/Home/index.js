import React from 'react';
import { Layout, Card, Row, Col, Button, Typography, Space } from 'antd';
import { LineChartOutlined, BarChartOutlined, DollarOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Title, Paragraph } = Typography;
const { Content } = Layout;

const Home = () => {
  const navigate = useNavigate();

  const handleStartAnalysis = () => {
    navigate('/stock-dashboard');
  };

  return (
    <Layout style={{ minHeight: '100vh', backgroundColor: '#141213' }}>
      <Content style={{ padding: '50px', backgroundColor: '#141213' }}>
        {/* 页面标题 */}
        <div style={{ textAlign: 'center', marginBottom: '50px' }}>
          <Title level={1} style={{ color: '#ffffff', marginBottom: '16px' }}>
            📈 股票大单数据分析平台
          </Title>
          <Paragraph style={{ fontSize: '18px', color: '#888', maxWidth: '600px', margin: '0 auto' }}>
            专业的股票大单数据实时分析工具，帮您精准把握市场资金流向，捕捉主力动向
          </Paragraph>
        </div>

        {/* 功能特色 */}
        <Row gutter={[24, 24]} style={{ marginBottom: '50px' }}>
          <Col span={6}>
            <Card 
              className="feature-card"
              style={{ 
                backgroundColor: '#1f1f1f', 
                borderColor: '#333',
                textAlign: 'center',
                height: '200px'
              }}
            >
              <LineChartOutlined style={{ fontSize: '48px', color: '#1890ff', marginBottom: '16px' }} />
              <Title level={4} style={{ color: '#ffffff', marginBottom: '8px' }}>实时分时图</Title>
              <Paragraph style={{ color: '#888' }}>
                实时展示股票价格走势、成交量变化，支持主力线和散户线分析
              </Paragraph>
            </Card>
          </Col>
          <Col span={6}>
            <Card 
              className="feature-card"
              style={{ 
                backgroundColor: '#1f1f1f', 
                borderColor: '#333',
                textAlign: 'center',
                height: '200px'
              }}
            >
              <DollarOutlined style={{ fontSize: '48px', color: '#52c41a', marginBottom: '16px' }} />
              <Title level={4} style={{ color: '#ffffff', marginBottom: '8px' }}>大单监控</Title>
              <Paragraph style={{ color: '#888' }}>
                监控30万以上大单交易，自动分级统计，掌握主力资金动向
              </Paragraph>
            </Card>
          </Col>
          <Col span={6}>
            <Card 
              className="feature-card"
              style={{ 
                backgroundColor: '#1f1f1f', 
                borderColor: '#333',
                textAlign: 'center',
                height: '200px'
              }}
            >
              <BarChartOutlined style={{ fontSize: '48px', color: '#faad14', marginBottom: '16px' }} />
              <Title level={4} style={{ color: '#ffffff', marginBottom: '8px' }}>资金流向</Title>
              <Paragraph style={{ color: '#888' }}>
                实时计算买卖资金流向，净流入统计，买卖力量对比分析
              </Paragraph>
            </Card>
          </Col>
          <Col span={6}>
            <Card 
              className="feature-card"
              style={{ 
                backgroundColor: '#1f1f1f', 
                borderColor: '#333',
                textAlign: 'center',
                height: '200px'
              }}
            >
              <SearchOutlined style={{ fontSize: '48px', color: '#ff4d4f', marginBottom: '16px' }} />
              <Title level={4} style={{ color: '#ffffff', marginBottom: '8px' }}>智能搜索</Title>
              <Paragraph style={{ color: '#888' }}>
                支持股票代码、名称快速搜索，智能提示，一键跳转分析
              </Paragraph>
            </Card>
          </Col>
        </Row>

        {/* 快速开始 */}
        <div style={{ textAlign: 'center', marginBottom: '50px' }}>
          <Card 
            style={{ 
              backgroundColor: '#1f1f1f', 
              borderColor: '#333',
              maxWidth: '500px',
              margin: '0 auto'
            }}
          >
            <Title level={3} style={{ color: '#ffffff', marginBottom: '20px' }}>
              立即开始股票分析
            </Title>
            <Paragraph style={{ color: '#888', marginBottom: '30px' }}>
              输入股票代码或名称，开始您的专业级股票大单分析之旅
            </Paragraph>
            <Button 
              type="primary" 
              size="large"
              onClick={handleStartAnalysis}
              style={{
                height: '50px',
                fontSize: '16px',
                fontWeight: 'bold',
                background: 'linear-gradient(135deg, #1890ff 0%, #40a9ff 100%)',
                border: 'none'
              }}
            >
              开始分析 →
            </Button>
          </Card>
        </div>

        {/* 数据说明 */}
        <Row gutter={[24, 24]}>
          <Col span={8}>
            <Card 
              title="数据级别"
              style={{ 
                backgroundColor: '#1f1f1f', 
                borderColor: '#333'
              }}
              headStyle={{ color: '#ffffff', borderBottomColor: '#333' }}
            >
              <Space direction="vertical" style={{ width: '100%' }}>
                <div style={{ color: '#ff1744' }}>≥300万：超大单（主力机构）</div>
                <div style={{ color: '#ff6600' }}>≥100万：大单（中等资金）</div>
                <div style={{ color: '#ff9900' }}>≥50万：中单（活跃资金）</div>
                <div style={{ color: '#52c41a' }}>≥30万：小单（散户资金）</div>
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card 
              title="更新频率"
              style={{ 
                backgroundColor: '#1f1f1f', 
                borderColor: '#333'
              }}
              headStyle={{ color: '#ffffff', borderBottomColor: '#333' }}
            >
              <Space direction="vertical" style={{ width: '100%', color: '#888' }}>
                <div>分时数据：每分钟更新</div>
                <div>大单数据：实时推送</div>
                <div>基础信息：每30秒刷新</div>
                <div>交易时间：9:30-15:00</div>
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card 
              title="功能说明"
              style={{ 
                backgroundColor: '#1f1f1f', 
                borderColor: '#333'
              }}
              headStyle={{ color: '#ffffff', borderBottomColor: '#333' }}
            >
              <Space direction="vertical" style={{ width: '100%', color: '#888' }}>
                <div>支持A股全市场股票</div>
                <div>多维度数据筛选</div>
                <div>可视化图表分析</div>
                <div>历史数据回放</div>
              </Space>
            </Card>
          </Col>
        </Row>
      </Content>
    </Layout>
  );
};

export default Home; 