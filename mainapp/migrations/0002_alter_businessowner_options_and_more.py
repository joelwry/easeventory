# Generated by Django 4.2.7 on 2025-06-11 17:28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('mainapp', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='businessowner',
            options={'verbose_name': 'Business Owner', 'verbose_name_plural': 'Business Owners'},
        ),
        migrations.AlterField(
            model_name='businessowner',
            name='address',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='businessowner',
            name='groups',
            field=models.ManyToManyField(blank=True, help_text='The groups this user belongs to.', related_name='business_owner_set', to='auth.group', verbose_name='groups'),
        ),
        migrations.AlterField(
            model_name='businessowner',
            name='user_permissions',
            field=models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='business_owner_set', to='auth.permission', verbose_name='user permissions'),
        ),
        migrations.AlterField(
            model_name='category',
            name='business_owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='categories', to='mainapp.businessowner'),
        ),
        migrations.AlterField(
            model_name='customer',
            name='business_owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customers', to='mainapp.businessowner'),
        ),
        migrations.AlterField(
            model_name='inventoryitem',
            name='business_owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inventory_items', to='mainapp.businessowner'),
        ),
        migrations.AlterField(
            model_name='sale',
            name='business_owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sales', to='mainapp.businessowner'),
        ),
    ]
