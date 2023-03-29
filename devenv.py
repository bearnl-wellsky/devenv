import argparse
from pathlib import Path
import boto3
import configparser
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from git import Repo


def setup_claire_amplify(config, branch: str, env_name: str,
    bretha_graphql_endpoint: str, shared_data_with: str):
    assert branch, f'Branch is not set'
    assert env_name, f'Environment name is not set'
    assert bretha_graphql_endpoint, f'Bretha graphql endpoint is not set'
    assert shared_data_with, f'Shared data with is not set'

    print('Creating claire Amplify environment', env_name)
    prod_config = config['claire']

    client = boto3.client("amplify")

    if setup_deployment_bucket(env_name.lower()):
        print(f"Deployment bucket is now setup 👍")
    else:
        print(f'Deployment bucket already exists')

    try:
        client.create_branch(
            appId=prod_config['app_id'],
            branchName=branch,
            stage="DEVELOPMENT",
            enableNotification=False,
            enableAutoBuild=True,
            enableBasicAuth=False,
            tags={'name': f'claire-{env_name}'},
            displayName=env_name.lower(),
            environmentVariables={
                'BRETHA_GRAPHQL_ENDPOINT': bretha_graphql_endpoint,
                'SHARED_DATA_WITH': shared_data_with,
            }
        )
        print('Created Amplify branch')
    except ClientError as e:
        print(f"Call to the Amplify Console throw an exception: {e}")
        return

    client.start_job(
        appId=prod_config['app_id'],
        branchName=branch,
        jobType="RELEASE",
        jobReason="Initial environment setup",
    )
    print('Started Amplify job')

    print("Done setting up development environment 😎")


def setup_wellsky_apps_amplify(config, branch: str, env_name: str):
    assert branch, f'Branch is not set'
    assert env_name, f'Environment name is not set'

    print('Creating wellsky apps branch', env_name)
    prod_config = config['wellsky-apps']

    client = boto3.client("amplify")

    try:
        client.create_branch(
            appId=prod_config['app_id'],
            branchName=branch,
            stage="DEVELOPMENT",
            enableNotification=False,
            enableAutoBuild=True,
            enableBasicAuth=False,
            tags={'name': f'wellsky-apps-{env_name}'},
            displayName=env_name.lower()
        )
        print('Created Amplify branch')
    except ClientError as e:
        print(f"Call to the Amplify Console throw an exception: {e}")
        return

    client.start_job(
        appId=prod_config['app_id'],
        branchName=branch,
        jobType="RELEASE",
        jobReason="Initial environment setup",
    )
    print('Started Amplify job')

    print("Done setting up development environment 😎")


def setup_deployment_bucket(stage):
    s3_client = boto3.client("s3")
    bucket_name = f"serverless-deployment-state-{stage.lower()}"

    try:
        s3_client.create_bucket(
            ACL="private",
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": "us-west-2"},
        )
    except ClientError as e:
        print(f"Unable to create bucket {bucket_name}", e)
        return False

    s3_client.put_bucket_encryption(
        Bucket=bucket_name,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ]
        },
    )
    s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    return True


def remove_amplify(config, product, env_name: str):
    assert product, f'Product is not set'
    assert env_name, f'Environment name is not set'

    print('Removing branch from amplify', env_name)
    client = boto3.client("amplify")
    try:
        client.delete_branch(
            appId=config[product]['app_id'],
            branchName=env_name
        )
    except ClientError as e:
        print(f"Unable to remove Amplify branch: {e}")
        return
    print('Done')


def setup_git(config: configparser.ConfigParser, product: str, branch_name: str,
    no_create=False, ignore_non_existing=False, reset_only=False):
    path = config[product]['path']
    assert Path.exists(path), f'Path {path} does not exist'
    assert product, f'Product is not set'
    assert branch_name, f'Branch name is not set'

    print('Setting up git for', product, 'in', path)
    repo = Repo(path)
    assert not repo.bare

    if (not no_create or reset_only) and 'default-branch' in config[product]:
        default_branch = config[product]['default-branch']
        print('Switching to default branch', default_branch)
        if repo.is_dirty():
            raise ValueError('Repo is dirty, I am not sure if it is safe to switch to default branch. Aborting')
        repo.git.checkout(default_branch)
    if reset_only:
        return

    branch_names = [h.name for h in repo.branches]
    if branch_name not in branch_names:
        if no_create and ignore_non_existing:
            print(f'Branch {branch_name} does not exist')
        elif no_create:
            raise ValueError(f'Branch {branch_name} does not exist')
        else:
            print(f'Creating branch {branch_name}')
            repo.create_head(branch_name)
            repo.remote(name='origin').push(branch_name)
    elif repo.is_dirty():
        raise ValueError('Repo is dirty, I am not sure if it is safe to switch to branch. Aborting')
    print(f'Checking out branch {branch_name}')
    repo.git.checkout(branch_name)


def copy_data(dto: str, dfrom: str):
    raise NotImplementedError('We are not there yet')


if __name__ == '__main__':
    load_dotenv()
    config = configparser.ConfigParser()
    config.read('config.ini')

    # regular arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--branch', help='Local Git branch name')
    parser.add_argument('--env', help='Amplify Environment name, no slash allowed')
    parser.add_argument('--remote-only', action='store_true', help='Do not create local Git branch')
    parser.add_argument('--local-only', action='store_true', help='Do not create Amplify environment')
    parser.add_argument('--bretha-graphql-endpoint', default='http://graphql.claire-qa.clearcare.ninja')
    parser.add_argument('--remove', action='store_true', help='Remove environment')
    g_copy = parser.add_mutually_exclusive_group()
    g_copy.add_argument('--copy-data-from', action='store', help='Duplicate data from another environment')
    g_copy.add_argument('--share-data-with', action='store', help='Share data with another environment')
    g_product = parser.add_argument_group(title='product')
    g_product.add_argument('--claire', action='store_true', help='Enable setup of Claire')
    g_product.add_argument('--wellsky-apps', action='store_true', help='Enable setup of Wellsky Apps')
    subparsers = parser.add_subparsers()
    p_jira = subparsers.add_parser('jira', help='Shortcuts to setup environment based on JIRA tickets')
    p_jira.add_argument('ticket', nargs='?', help='JIRA ticket number, e.g., CW-2134')
    p_jira.add_argument('--new', action='store_true', help='Create new Amplify environment')
    args = parser.parse_args()

    if 'ticket' in args and args.ticket:
        args.local_only = True
        args.branch = f'issue/{args.ticket}'

        if args.new:
            args.env = f'{args.ticket}'
            args.share_data_with = 'qa'
            args.local_only = False
        else:
            if args.claire:
                setup_git(config, 'claire', args.branch, args.local_only, ignore_non_existing=True)
            if args.wellsky_apps:
                setup_git(config, 'wellsky-apps', args.branch, args.local_only, ignore_non_existing=True)
            exit(0)


    if not args.remote_only and args.branch:
        if args.claire:
            setup_git(config, 'claire', args.branch, args.local_only)
        if args.wellsky_apps:
            setup_git(config, 'wellsky-apps', args.branch, args.local_only)

    if not args.local_only:
        if args.remove:
            if args.claire:
                remove_amplify(config, 'claire', args.env)
            if args.wellsky_apps:
                remove_amplify(config, 'wellsky-apps', args.env)
        else:
            if args.claire:
                setup_claire_amplify(config,
                    args.branch, args.env,
                    args.bretha_graphql_endpoint, args.share_data_with
                    )
            if args.wellsky_apps:
                setup_wellsky_apps_amplify(config,
                    args.branch, args.env
                    )

            if args.copy_data_from:
                copy_data(args.env, args.copy_data_from)
