
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
    }

    environment {
        IMAGE_NAME = 'devops-task-tracker'
        IMAGE_TAG = 'ci'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Check Tool Versions') {
            steps {
                sh '''
                    set -eu
                    git --version
                    python3 --version
                    docker --version
                '''
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    set -eu
                    python3 -m venv .venv
                    .venv/bin/python -m pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
                    .venv/bin/python -m pytest \
                        --junitxml=pytest-results.xml
                '''
            }
            post {
                always {
                    junit testResults: 'pytest-results.xml',
                          allowEmptyResults: true
                }
            }
        }

        stage('Lint') {
            steps {
                sh '''
                    .venv/bin/flake8 app.py tests
                '''
            }
        }

        stage('Security Scan') {
            steps {
                sh '''
                    .venv/bin/bandit -r app.py
                    .venv/bin/pip-audit -r requirements.txt
                '''
            }
        }

        stage('Build Docker Image') {
            steps {
                sh '''
                    set -eu
                    docker build \
                        -t "${IMAGE_NAME}:${IMAGE_TAG}" .
                    docker image inspect "${IMAGE_NAME}:${IMAGE_TAG}"
                '''
            }
        }
    }

    post {
        success {
            echo 'CI passed: tests, lint, security checks and image build.'
        }

        failure {
            echo 'CI failed. Inspect the failed stage and console output.'
        }

        always {
            echo 'Task Tracker CI pipeline finished.'
        }
    }
}
