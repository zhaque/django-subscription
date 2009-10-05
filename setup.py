from setuptools import setup, find_packages

setup(name="django-subscription",
           version="0.1",
           description="Subscriptions based web app using django-paypal",
           author="CrowdSense",
           author_email="admin@crowdsense.com",
           packages=find_packages(),
           include_package_data=True,
)

