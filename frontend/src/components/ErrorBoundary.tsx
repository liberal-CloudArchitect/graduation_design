// 全局错误边界组件
import React from 'react';
import { Result, Button } from 'antd';

interface Props {
    children: React.ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

class ErrorBoundary extends React.Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
        console.error('ErrorBoundary caught:', error, errorInfo);
    }

    handleReload = () => {
        this.setState({ hasError: false, error: null });
        window.location.href = '/';
    };

    render() {
        if (this.state.hasError) {
            return (
                <div style={{ padding: 48, maxWidth: 600, margin: '0 auto', marginTop: '10vh' }}>
                    <Result
                        status="error"
                        title="页面出现了问题"
                        subTitle="抱歉，页面加载时出现了错误。请尝试刷新页面。"
                        extra={[
                            <Button key="reload" type="primary" onClick={this.handleReload}>
                                返回首页
                            </Button>,
                            <Button key="refresh" onClick={() => window.location.reload()}>
                                刷新页面
                            </Button>,
                        ]}
                    />
                    {process.env.NODE_ENV === 'development' && this.state.error && (
                        <pre style={{
                            marginTop: 24,
                            padding: 16,
                            background: '#f5f5f5',
                            borderRadius: 8,
                            fontSize: 12,
                            overflow: 'auto',
                        }}>
                            {this.state.error.message}
                            {'\n'}
                            {this.state.error.stack}
                        </pre>
                    )}
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;
