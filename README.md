# Gooee Alexa Control

An Alexa integration that uses Gooee's API for lighting control.

## Requirements

* Python 3.6 or higher
* AWS account
* Amazon Developer Account
* OAuth2 client ID and secret obtained by emailing <cloud-backend@gooee.com>

### Dev Requirements
This is meant to be ran in an AWS Lambda environment, but to run tests locally:
`pip install -r requirements.txt`

## Usage

Below are steps to deploy this Lambda function as an Alexa Smart Home Skill:

1. Create a Python 3.6 AWS Lambda function "from scratch" using your AWS account in the region you plan to distribute the Alexa skill.
2. In the Designer section, select "Alexa Smart Home" as a trigger.
3. A new section "Configure triggers" should prompt you to provide an Application ID. Open the "Alexa section" link **IN A NEW TAB.**
4. In the new tab, login using your Amazon Developer Account and click "Create Skill" > "Smart Home"
5. Copy the Skill ID to your clipboard and flip back to the AWS Lambda tab. Use this as the input for the "Application ID", then Save.
6. Copy the Lambda ARN at the top right, flip back to the Amazon Developer tab, and use this as the "Default endpoint", then Save.
7. In the Function code section, select "Upload a .ZIP file" from the "Code entry type" drop-down.
8. Run `make` *or* Zip this directory. Provide `dist.zip` or your created zip as the upload, then Save.
9. Afterwards, you will need to setup Account Linking using the Amazon Developer Console. Use the Client ID and Secret from the requirements section.

### Running Tests

After installing the requirements, run them locally by executing `pytest` *or* `make test`

## Future Plans

* Implement a `SceneController`.
