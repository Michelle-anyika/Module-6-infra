"""Module 6 network architecture - diagram as code.

Render:  pip install diagrams  (requires Graphviz on PATH)
         python diagrams/architecture.py   ->  diagrams/architecture.png
"""
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, ElasticContainerServiceService, Fargate
from diagrams.aws.database import ElasticacheForRedis, RDSPostgresqlInstance
from diagrams.aws.devtools import Codedeploy, Codepipeline
from diagrams.aws.integration import Eventbridge
from diagrams.aws.management import Cloudformation, Cloudwatch
from diagrams.aws.network import ALB, Endpoint, InternetGateway
from diagrams.aws.security import IAMRole, SecretsManager
from diagrams.aws.storage import S3
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Users
from diagrams.onprem.vcs import Github
from diagrams.aws.database import RDS

graph_attr = {"fontsize": "20", "pad": "0.5", "splines": "spline", "nodesep": "0.6", "ranksep": "0.9"}

with Diagram("Module 6 - ECS Fargate + RDS Proxy + ElastiCache (eu-north-1)",
             filename="diagrams/architecture", show=False, direction="LR", graph_attr=graph_attr):
    users = Users("Users")

    with Cluster("GitHub"):
        app_repo = Github("Module-6-app")
        infra_repo = Github("Module-6-infra")
        gha = GithubActions("build-and-push\n(OIDC)")

    with Cluster("AWS account - eu-north-1"):
        cfn = Cloudformation("CloudFormation\nGit sync")
        oidc_role = IAMRole("github-actions role\n(OIDC, no keys)")
        ecr = ECR("ECR\nmodule-6-dev-app")
        bundle = S3("Artifacts bucket\ndeploy/bundle.zip")
        events = Eventbridge("EventBridge\nECR PUSH rule")
        pipeline = Codepipeline("CodePipeline")
        codedeploy = Codedeploy("CodeDeploy\nblue/green")
        logs = Cloudwatch("CloudWatch Logs\n/ecs/module-6-dev-app")
        secrets = SecretsManager("Secrets Manager\nRDS + Redis secrets")

        with Cluster("VPC 10.0.0.0/16 (2 AZs)"):
            igw = InternetGateway("IGW")

            with Cluster("Public subnets 10.0.0-1.0/24  [alb-sg]"):
                alb = ALB("ALB\n:80 prod / :8080 test")

            with Cluster("App subnets 10.0.10-11.0/24  [ecs-sg]"):
                svc = ElasticContainerServiceService("ECS service\n1-4 tasks, CPU 60%")
                tasks = [Fargate("task (AZ a)"), Fargate("task (AZ b)")]

            with Cluster("Interface endpoints in app subnets  [vpce-sg]"):
                vpce = Endpoint("ecr.api / ecr.dkr\nlogs / secretsmanager")
                s3gw = Endpoint("S3 gateway")

            with Cluster("Proxy subnets 10.0.30-31.0/24  [rdsproxy-sg]"):
                proxy = RDS("RDS Proxy\nIAM auth + TLS")

            with Cluster("DB subnets 10.0.20-21.0/24  [rds-sg]"):
                db = RDSPostgresqlInstance("PostgreSQL 16\ndb.t3.micro")

            with Cluster("Cache subnets 10.0.40-41.0/24  [redis-sg]"):
                redis = ElasticacheForRedis("Redis 7.1\nprimary + replica")

    users >> Edge(label="HTTP") >> igw >> alb >> Edge(label=":8080") >> svc >> tasks
    tasks[0] >> Edge(label="writes / misses\n5432 TLS") >> proxy >> Edge(label="5432") >> db
    tasks[0] >> Edge(label="reads\n6379 TLS", color="firebrick") >> redis
    tasks[1] >> Edge(style="dashed", label="443") >> vpce
    tasks[1] >> Edge(style="dashed") >> s3gw
    vpce >> Edge(style="dashed") >> [ecr, logs, secrets]
    proxy >> Edge(style="dotted") >> secrets

    infra_repo >> Edge(label="deployment files") >> cfn
    app_repo >> Edge(label="push") >> gha >> Edge(label="AssumeRoleWithWebIdentity") >> oidc_role
    gha >> Edge(label="image") >> ecr
    gha >> Edge(label="taskdef + appspec") >> bundle
    ecr >> Edge(label="PUSH event") >> events >> pipeline
    bundle >> pipeline >> codedeploy >> Edge(label="shift blue -> green") >> alb
