// 登录页面
import React from 'react';
import { Form, Input, Button, Card, Typography, message } from 'antd';
import { LockOutlined, MailOutlined } from '@ant-design/icons';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';
import './index.css';

const { Title, Text } = Typography;

const Login: React.FC = () => {
    const navigate = useNavigate();
    const { login, isLoading } = useAuthStore();
    const [form] = Form.useForm();

    const handleSubmit = async (values: { email: string; password: string }) => {
        try {
            await login(values);
            message.success('登录成功');
            navigate('/');
        } catch (error: unknown) {
            const err = error as { response?: { data?: { detail?: string } } };
            if (err.response?.data?.detail) {
                message.error(err.response.data.detail);
            }
        }
    };

    return (
        <div className="login-container">
            <Card className="login-card">
                <div className="login-header">
                    <Title level={2}>文献分析平台</Title>
                    <Text type="secondary">基于RAG的智能文献问答系统</Text>
                </div>

                <Form
                    form={form}
                    name="login"
                    onFinish={handleSubmit}
                    size="large"
                    layout="vertical"
                >
                    <Form.Item
                        name="email"
                        rules={[
                            { required: true, message: '请输入邮箱' },
                            { type: 'email', message: '请输入有效的邮箱地址' },
                        ]}
                    >
                        <Input
                            prefix={<MailOutlined />}
                            placeholder="邮箱"
                        />
                    </Form.Item>

                    <Form.Item
                        name="password"
                        rules={[{ required: true, message: '请输入密码' }]}
                    >
                        <Input.Password
                            prefix={<LockOutlined />}
                            placeholder="密码"
                        />
                    </Form.Item>

                    <Form.Item>
                        <Button
                            type="primary"
                            htmlType="submit"
                            loading={isLoading}
                            block
                        >
                            登录
                        </Button>
                    </Form.Item>

                    <div className="login-footer">
                        <Text>还没有账号？</Text>
                        <Link to="/register">立即注册</Link>
                    </div>
                </Form>
            </Card>
        </div>
    );
};

export default Login;
