from setuptools import setup

setup(name='smalanalysis',
      version='0.1a2',
      description='Android Bytecode Analysis Tools (Androguard-based)',
      long_description='Android Bytecode Analysis Tools using Androguard',
      classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Topic :: Software Development',
      ],
      python_requires='~=3.6',
      keywords='smali android apk androguard',
      url='https://github.com/v-m/smalanalysis',
      author='Vincenzo Musco',
      author_email='muscovin@gmail.com',
      license='MIT',
      packages=['smalanalysis', 'smalanalysis.smali', 'smalanalysis.tools'],
      install_requires=[
          'androguard>=4.1.0',
      ],
      include_package_data=True,
      zip_safe=False)
